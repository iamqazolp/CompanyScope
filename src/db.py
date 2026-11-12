import datetime
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import sqlite3
import time
from typing import Any
import uuid

from src.config import (
    DAILY_QUERY_LIMIT,
    DATABASE_URL,
    GEMINI_EMBEDDING_DIM,
    PROCESSED_DIR,
    QUOTA_SECRET,
)

_pg_schema_ready = False
_sqlite_schema_ready = False


def is_postgres_enabled() -> bool:
    """Returns True when a cloud Postgres DATABASE_URL is configured."""
    return bool(DATABASE_URL)


def _get_sqlite_path() -> Path:
    try:
        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        test_path = PROCESSED_DIR / "local_state.db"
        if os.access(PROCESSED_DIR, os.W_OK):
            return test_path
    except Exception:
        pass
    return Path("/tmp/companyscope_state.db")


def _get_sqlite_conn() -> sqlite3.Connection:
    global _sqlite_schema_ready
    conn = sqlite3.connect(str(_get_sqlite_path()), timeout=10.0)
    conn.row_factory = sqlite3.Row
    if not _sqlite_schema_ready:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS guest_quotas (
                quota_key TEXT NOT NULL,
                usage_date TEXT NOT NULL,
                used_count INTEGER NOT NULL DEFAULT 0,
                updated_at REAL NOT NULL,
                PRIMARY KEY (quota_key, usage_date)
            );
            CREATE TABLE IF NOT EXISTS xbrl_cache (
                ticker TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                cached_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS shared_reports (
                slug TEXT PRIMARY KEY,
                question TEXT NOT NULL,
                tickers_json TEXT NOT NULL,
                mode TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS market_cache (
                cache_key TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                cached_at REAL NOT NULL
            );
            """
        )
        conn.commit()
        _sqlite_schema_ready = True
    return conn


def _get_pg_conn() -> Any:
    import psycopg

    return psycopg.connect(DATABASE_URL, connect_timeout=10, autocommit=True)


def ensure_pg_schema() -> None:
    """Creates pgvector extension, filing_chunks, quota, cache, and report tables idempotently."""
    global _pg_schema_ready
    if _pg_schema_ready or not is_postgres_enabled():
        return

    dim = int(GEMINI_EMBEDDING_DIM)
    with _get_pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS filing_chunks (
                    id TEXT PRIMARY KEY,
                    chunk_id TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    year INTEGER NOT NULL,
                    filing_type TEXT NOT NULL,
                    section TEXT NOT NULL,
                    chunk_level TEXT NOT NULL DEFAULT 'leaf',
                    chunk_text TEXT NOT NULL,
                    embedding vector({dim}) NOT NULL,
                    tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', chunk_text)) STORED,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_filing_chunks_meta ON filing_chunks (ticker, year, section);"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_filing_chunks_tsv ON filing_chunks USING GIN (tsv);"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_filing_chunks_hnsw ON filing_chunks USING hnsw (embedding vector_cosine_ops);"
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS guest_quotas (
                    quota_key TEXT NOT NULL,
                    usage_date DATE NOT NULL,
                    used_count INTEGER NOT NULL DEFAULT 0,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (quota_key, usage_date)
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS xbrl_cache (
                    ticker TEXT PRIMARY KEY,
                    payload_json JSONB NOT NULL,
                    cached_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS shared_reports (
                    slug TEXT PRIMARY KEY,
                    question TEXT NOT NULL,
                    tickers_json JSONB NOT NULL,
                    mode TEXT NOT NULL,
                    payload_json JSONB NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS market_cache (
                    cache_key TEXT PRIMARY KEY,
                    payload_json JSONB NOT NULL,
                    cached_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
    _pg_schema_ready = True


def _vec_literal(vec: list[float]) -> str:
    return "[" + ",".join(f"{v:.7f}" for v in vec) + "]"


# ---------------------------------------------------------------------------
# Cloud pgvector + tsvector Indexing & Hybrid RRF Search
# ---------------------------------------------------------------------------


def upsert_chunks_pg(
    rows: list[dict[str, Any]],
    embeddings: list[list[float]],
    ticker_filter: str | None = None,
) -> int:
    """Replaces target ticker chunks (or full table) and batch-upserts vectors in Postgres."""
    ensure_pg_schema()
    if not rows:
        return 0

    with _get_pg_conn() as conn:
        with conn.cursor() as cur:
            if ticker_filter:
                cur.execute(
                    "DELETE FROM filing_chunks WHERE ticker = %s;",
                    (ticker_filter.upper(),),
                )
            else:
                cur.execute("TRUNCATE TABLE filing_chunks;")

            batch_params = [
                (
                    str(r["id"]),
                    str(r["chunk_id"]),
                    str(r["ticker"]).upper(),
                    int(r["year"]),
                    str(r["filing_type"]),
                    str(r["section"]),
                    str(r.get("chunk_level", "leaf")),
                    str(r["chunk_text"]),
                    _vec_literal(emb),
                )
                for r, emb in zip(rows, embeddings)
            ]

            cur.executemany(
                """
                INSERT INTO filing_chunks (
                    id, chunk_id, ticker, year, filing_type, section, chunk_level, chunk_text, embedding
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::vector)
                ON CONFLICT (id) DO UPDATE SET
                    chunk_id = EXCLUDED.chunk_id,
                    ticker = EXCLUDED.ticker,
                    year = EXCLUDED.year,
                    filing_type = EXCLUDED.filing_type,
                    section = EXCLUDED.section,
                    chunk_level = EXCLUDED.chunk_level,
                    chunk_text = EXCLUDED.chunk_text,
                    embedding = EXCLUDED.embedding,
                    updated_at = NOW();
                """,
                batch_params,
            )
    return len(rows)


def has_ticker_chunks_pg(ticker: str) -> bool:
    ensure_pg_schema()
    with _get_pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM filing_chunks WHERE ticker = %s LIMIT 1;",
                (ticker.upper().strip(),),
            )
            return cur.fetchone() is not None


def get_index_stats_pg() -> dict[str, Any]:
    ensure_pg_schema()
    with _get_pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT ticker, year, section, COUNT(*) AS cnt
                FROM filing_chunks
                GROUP BY ticker, year, section;
                """
            )
            agg_rows = cur.fetchall()

    total = 0
    tickers: dict[str, dict[str, Any]] = {}
    for t_raw, yr, sec, cnt in agg_rows:
        t = str(t_raw).upper()
        c = int(cnt)
        total += c
        if t not in tickers:
            tickers[t] = {"chunks": 0, "years": set(), "sections": set()}
        tickers[t]["chunks"] += c
        if yr is not None:
            tickers[t]["years"].add(int(yr))
        if sec:
            tickers[t]["sections"].add(str(sec))

    formatted = {
        t: {
            "chunks": info["chunks"],
            "years": sorted(list(info["years"])),
            "sections": sorted(list(info["sections"])),
        }
        for t, info in sorted(tickers.items())
    }
    return {"total_chunks": total, "tickers": formatted, "backend": "pgvector"}


def _execute_pg_rrf(
    query: str,
    query_vec: list[float],
    ticker: str | None,
    year_int: int | None,
    section_clean: str | None,
    candidate_pool: int,
) -> tuple[list[tuple[Any, ...]], list[tuple[Any, ...]]]:
    where_clauses: list[str] = []
    where_params: list[Any] = []
    if ticker:
        where_clauses.append("ticker = %s")
        where_params.append(ticker.upper().strip())
    if year_int is not None:
        where_clauses.append("year = %s")
        where_params.append(year_int)
    if section_clean:
        where_clauses.append("section = %s")
        where_params.append(section_clean)

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    vec_str = _vec_literal(query_vec)

    with _get_pg_conn() as conn:
        with conn.cursor() as cur:
            dense_sql = f"""
                SELECT chunk_id, ticker, year, section, chunk_level, chunk_text
                FROM filing_chunks
                {where_sql}
                ORDER BY embedding <=> %s::vector
                LIMIT %s;
            """
            cur.execute(dense_sql, [*where_params, vec_str, candidate_pool])
            dense_rows = cur.fetchall()

            lex_where = (
                f"{where_sql} AND tsv @@ websearch_to_tsquery('english', %s)"
                if where_sql
                else "WHERE tsv @@ websearch_to_tsquery('english', %s)"
            )
            lex_sql = f"""
                SELECT chunk_id, ticker, year, section, chunk_level, chunk_text
                FROM filing_chunks
                {lex_where}
                ORDER BY ts_rank_cd(tsv, websearch_to_tsquery('english', %s)) DESC
                LIMIT %s;
            """
            cur.execute(lex_sql, [*where_params, query, query, candidate_pool])
            lex_rows = cur.fetchall()

    return dense_rows, lex_rows


def hybrid_search_pg(
    query: str,
    query_vec: list[float],
    ticker: str | None = None,
    year: str | int | None = None,
    section: str | None = None,
    k_limit: int = 4,
) -> list[dict[str, Any]]:
    """Runs Hybrid RRF search combining pgvector cosine distance and Postgres full-text search."""
    ensure_pg_schema()
    year_int: int | None = None
    if year is not None and str(year).strip() != "":
        try:
            year_int = int(str(year).strip())
        except ValueError:
            year_int = None

    sec_clean: str | None = None
    if section and str(section).strip():
        sec_clean = str(section).strip()
        if not sec_clean.lower().startswith("item"):
            sec_clean = f"Item {sec_clean}"

    candidate_pool = max(k_limit * 4, 15)
    dense_rows, lex_rows = _execute_pg_rrf(
        query, query_vec, ticker, year_int, sec_clean, candidate_pool
    )

    # Relax section filter if strict section filter returned 0 hits
    if not dense_rows and not lex_rows and sec_clean and (ticker or year_int is not None):
        dense_rows, lex_rows = _execute_pg_rrf(
            query, query_vec, ticker, year_int, None, candidate_pool
        )

    candidates: dict[str, dict[str, Any]] = {}
    dense_rank_map: dict[str, int] = {}
    lex_rank_map: dict[str, int] = {}

    for rank, (cid, tkr, yr, sec, lvl, txt) in enumerate(dense_rows):
        cid_s = str(cid)
        if cid_s not in dense_rank_map:
            dense_rank_map[cid_s] = rank
            candidates[cid_s] = {
                "chunk_id": cid_s,
                "ticker": tkr,
                "year": yr,
                "section": sec,
                "chunk_level": lvl or "leaf",
                "chunk_text": txt,
            }

    for rank, (cid, tkr, yr, sec, lvl, txt) in enumerate(lex_rows):
        cid_s = str(cid)
        if cid_s not in lex_rank_map:
            lex_rank_map[cid_s] = rank
        if cid_s not in candidates:
            candidates[cid_s] = {
                "chunk_id": cid_s,
                "ticker": tkr,
                "year": yr,
                "section": sec,
                "chunk_level": lvl or "leaf",
                "chunk_text": txt,
            }

    rrf_k = 60
    is_broad = any(
        kw in query.lower()
        for kw in ("summarize", "summary", "overview", "tell me about", "main", "general")
    )

    scored: list[tuple[float, dict[str, Any]]] = []
    for cid_s, item in candidates.items():
        score = 0.0
        if cid_s in dense_rank_map:
            score += 1.0 / (rrf_k + dense_rank_map[cid_s] + 1)
        if cid_s in lex_rank_map:
            score += 1.0 / (rrf_k + lex_rank_map[cid_s] + 1)
        if is_broad and item.get("chunk_level") == "summary":
            score += 0.008
        scored.append((score, item))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored[:k_limit]]


def get_section_chunks_pg(
    ticker: str,
    section: str,
    year: int | None = None,
) -> list[dict[str, Any]]:
    """Fetches indexed chunks for a specific section (e.g. 8-K Item 2.02) from Postgres."""
    ensure_pg_schema()
    clauses = ["ticker = %s", "section = %s"]
    params: list[Any] = [ticker.upper().strip(), section]
    if year is not None:
        clauses.append("year = %s")
        params.append(int(year))

    sql = f"""
        SELECT chunk_id, ticker, year, section, chunk_level, chunk_text
        FROM filing_chunks
        WHERE {" AND ".join(clauses)}
        ORDER BY year DESC, id ASC
        LIMIT 60;
    """
    with _get_pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

    return [
        {
            "chunk_id": str(cid),
            "ticker": tkr,
            "year": yr,
            "section": sec,
            "chunk_level": lvl or "leaf",
            "chunk_text": txt,
        }
        for cid, tkr, yr, sec, lvl, txt in rows
    ]


# ---------------------------------------------------------------------------
# No-Login Daily Guest Quota (5 Queries / UTC Day)
# ---------------------------------------------------------------------------


def make_guest_cookie() -> str:
    raw_id = uuid.uuid4().hex[:16]
    sig = hmac.new(QUOTA_SECRET.encode(), raw_id.encode(), hashlib.sha256).hexdigest()[:16]
    return f"{raw_id}.{sig}"


def verify_guest_cookie(cookie_val: str | None) -> str | None:
    if not cookie_val or "." not in cookie_val:
        return None
    raw_id, sig = cookie_val.split(".", 1)
    expected = hmac.new(
        QUOTA_SECRET.encode(), raw_id.encode(), hashlib.sha256
    ).hexdigest()[:16]
    if hmac.compare_digest(sig, expected):
        return raw_id
    return None


def derive_quota_keys(client_ip: str, guest_id: str) -> tuple[str, str]:
    """Returns (ip_key, cookie_key) hashed with HMAC-SHA256 so raw IPs are never stored."""
    ip_norm = (client_ip or "unknown").strip().lower()
    ip_hash = hmac.new(QUOTA_SECRET.encode(), f"ip:{ip_norm}".encode(), hashlib.sha256).hexdigest()[:24]
    cookie_hash = hmac.new(QUOTA_SECRET.encode(), f"gid:{guest_id}".encode(), hashlib.sha256).hexdigest()[:24]
    return f"ip_{ip_hash}", f"gid_{cookie_hash}"


def _utc_today_and_reset() -> tuple[str, str]:
    now = datetime.datetime.now(datetime.timezone.utc)
    today_str = now.date().isoformat()
    tomorrow = datetime.datetime.combine(
        now.date() + datetime.timedelta(days=1),
        datetime.time(0, 0, 0, tzinfo=datetime.timezone.utc),
    )
    return today_str, tomorrow.isoformat()


def get_quota_status(
    client_ip: str,
    guest_id: str,
    daily_limit: int = DAILY_QUERY_LIMIT,
) -> dict[str, Any]:
    """Reads remaining daily queries without incrementing usage."""
    ip_key, gid_key = derive_quota_keys(client_ip, guest_id)
    today_str, reset_at = _utc_today_and_reset()
    used = 0

    if is_postgres_enabled():
        try:
            ensure_pg_schema()
            with _get_pg_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT COALESCE(MAX(used_count), 0)
                        FROM guest_quotas
                        WHERE usage_date = %s::date AND quota_key IN (%s, %s);
                        """,
                        (today_str, ip_key, gid_key),
                    )
                    row = cur.fetchone()
                    used = int(row[0]) if row and row[0] is not None else 0
        except Exception:
            used = 0
    else:
        conn = _get_sqlite_conn()
        try:
            row = conn.execute(
                """
                SELECT COALESCE(MAX(used_count), 0) AS m
                FROM guest_quotas
                WHERE usage_date = ? AND quota_key IN (?, ?);
                """,
                (today_str, ip_key, gid_key),
            ).fetchone()
            used = int(row["m"]) if row else 0
        finally:
            conn.close()

    remaining = max(0, daily_limit - used)
    return {
        "limit": daily_limit,
        "used": min(used, daily_limit),
        "remaining": remaining,
        "reset_at": reset_at,
    }


def consume_quota(
    client_ip: str,
    guest_id: str,
    daily_limit: int = DAILY_QUERY_LIMIT,
) -> tuple[bool, dict[str, Any]]:
    """
    Atomically checks and consumes 1 query against the daily guest limit across BOTH
    hashed IP and signed guest cookie (preventing cookie-clearing bypasses).
    """
    status = get_quota_status(client_ip, guest_id, daily_limit=daily_limit)
    if status["remaining"] <= 0:
        return False, status

    ip_key, gid_key = derive_quota_keys(client_ip, guest_id)
    today_str, reset_at = _utc_today_and_reset()
    keys = [ip_key] if ip_key == gid_key else [ip_key, gid_key]

    if is_postgres_enabled():
        ensure_pg_schema()
        with _get_pg_conn() as conn:
            with conn.cursor() as cur:
                for k in keys:
                    cur.execute(
                        """
                        INSERT INTO guest_quotas (quota_key, usage_date, used_count, updated_at)
                        VALUES (%s, %s::date, 1, NOW())
                        ON CONFLICT (quota_key, usage_date) DO UPDATE
                        SET used_count = guest_quotas.used_count + 1, updated_at = NOW();
                        """,
                        (k, today_str),
                    )
    else:
        now_ts = time.time()
        conn = _get_sqlite_conn()
        try:
            for k in keys:
                conn.execute(
                    """
                    INSERT INTO guest_quotas (quota_key, usage_date, used_count, updated_at)
                    VALUES (?, ?, 1, ?)
                    ON CONFLICT (quota_key, usage_date) DO UPDATE
                    SET used_count = used_count + 1, updated_at = excluded.updated_at;
                    """,
                    (k, today_str, now_ts),
                )
            conn.commit()
        finally:
            conn.close()

    updated = get_quota_status(client_ip, guest_id, daily_limit=daily_limit)
    updated["reset_at"] = reset_at
    return True, updated


# ---------------------------------------------------------------------------
# XBRL Financial Summary Cache (24h TTL) & Shareable Research Reports
# ---------------------------------------------------------------------------


def get_cached_financials(ticker: str, ttl_seconds: int = 86400) -> list[dict[str, Any]] | None:
    clean = ticker.upper().strip()
    if is_postgres_enabled():
        try:
            ensure_pg_schema()
            with _get_pg_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT payload_json
                        FROM xbrl_cache
                        WHERE ticker = %s
                          AND cached_at >= NOW() - (%s * INTERVAL '1 second');
                        """,
                        (clean, ttl_seconds),
                    )
                    row = cur.fetchone()
                    if row and row[0]:
                        val = row[0]
                        return json.loads(val) if isinstance(val, str) else list(val)
        except Exception:
            return None
        return None

    conn = _get_sqlite_conn()
    try:
        row = conn.execute(
            "SELECT payload_json, cached_at FROM xbrl_cache WHERE ticker = ?;",
            (clean,),
        ).fetchone()
        if row and (time.time() - float(row["cached_at"]) <= ttl_seconds):
            return list(json.loads(row["payload_json"]))
    except Exception:
        return None
    finally:
        conn.close()
    return None


def set_cached_financials(ticker: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    clean = ticker.upper().strip()
    payload_str = json.dumps(rows)
    if is_postgres_enabled():
        try:
            ensure_pg_schema()
            with _get_pg_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO xbrl_cache (ticker, payload_json, cached_at)
                        VALUES (%s, %s::jsonb, NOW())
                        ON CONFLICT (ticker) DO UPDATE
                        SET payload_json = EXCLUDED.payload_json, cached_at = NOW();
                        """,
                        (clean, payload_str),
                    )
        except Exception:
            pass
        return

    conn = _get_sqlite_conn()
    try:
        conn.execute(
            """
            INSERT INTO xbrl_cache (ticker, payload_json, cached_at)
            VALUES (?, ?, ?)
            ON CONFLICT (ticker) DO UPDATE
            SET payload_json = excluded.payload_json, cached_at = excluded.cached_at;
            """,
            (clean, payload_str, time.time()),
        )
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()


def save_shared_report(
    question: str,
    tickers: list[str],
    mode: str,
    payload: dict[str, Any],
    custom_slug: str | None = None,
) -> str:
    prefix = "-".join(t.lower() for t in tickers[:3]) if tickers else "report"
    prefix = re.sub(r"[^a-z0-9-]+", "", prefix) or "report"
    slug = custom_slug or f"{prefix}-{uuid.uuid4().hex[:8]}"
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    tickers_str = json.dumps(tickers)
    payload_str = json.dumps(payload)

    if is_postgres_enabled():
        try:
            ensure_pg_schema()
            with _get_pg_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO shared_reports (slug, question, tickers_json, mode, payload_json, created_at)
                        VALUES (%s, %s, %s::jsonb, %s, %s::jsonb, NOW())
                        ON CONFLICT (slug) DO UPDATE
                        SET payload_json = EXCLUDED.payload_json;
                        """,
                        (slug, question, tickers_str, mode, payload_str),
                    )
            return slug
        except Exception:
            pass

    conn = _get_sqlite_conn()
    try:
        conn.execute(
            """
            INSERT INTO shared_reports (slug, question, tickers_json, mode, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (slug) DO UPDATE SET payload_json = excluded.payload_json;
            """,
            (slug, question, tickers_str, mode, payload_str, now_iso),
        )
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()
    return slug


def get_shared_report(slug: str) -> dict[str, Any] | None:
    if is_postgres_enabled():
        try:
            ensure_pg_schema()
            with _get_pg_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT slug, question, tickers_json, mode, payload_json, created_at
                        FROM shared_reports
                        WHERE slug = %s;
                        """,
                        (slug,),
                    )
                    row = cur.fetchone()
                    if row:
                        s, q, tk, md, pl, cat = row
                        return {
                            "slug": s,
                            "question": q,
                            "tickers": json.loads(tk) if isinstance(tk, str) else tk,
                            "mode": md,
                            "result": json.loads(pl) if isinstance(pl, str) else pl,
                            "created_at": cat.isoformat() if hasattr(cat, "isoformat") else str(cat),
                        }
        except Exception:
            pass

    conn = _get_sqlite_conn()
    try:
        row = conn.execute(
            """
            SELECT slug, question, tickers_json, mode, payload_json, created_at
            FROM shared_reports
            WHERE slug = ?;
            """,
            (slug,),
        ).fetchone()
        if row:
            return {
                "slug": row["slug"],
                "question": row["question"],
                "tickers": json.loads(row["tickers_json"]),
                "mode": row["mode"],
                "result": json.loads(row["payload_json"]),
                "created_at": row["created_at"],
            }
    except Exception:
        return None
    finally:
        conn.close()
    return None


def get_market_cache(cache_key: str, ttl_seconds: int = 300) -> Any | None:
    """Reads a TTL-cached JSON payload from Neon Postgres or local SQLite."""
    if is_postgres_enabled():
        try:
            ensure_pg_schema()
            with _get_pg_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT payload_json
                        FROM market_cache
                        WHERE cache_key = %s
                          AND cached_at >= NOW() - (%s * INTERVAL '1 second');
                        """,
                        (cache_key, ttl_seconds),
                    )
                    row = cur.fetchone()
                    if row and row[0] is not None:
                        val = row[0]
                        return json.loads(val) if isinstance(val, str) else val
        except Exception:
            return None
        return None

    conn = _get_sqlite_conn()
    try:
        row = conn.execute(
            "SELECT payload_json, cached_at FROM market_cache WHERE cache_key = ?;",
            (cache_key,),
        ).fetchone()
        if row and (time.time() - float(row["cached_at"]) <= ttl_seconds):
            return json.loads(row["payload_json"])
    except Exception:
        return None
    finally:
        conn.close()
    return None


def set_market_cache(cache_key: str, payload: Any) -> None:
    """Persists a JSON payload into market_cache in Neon Postgres or local SQLite."""
    payload_str = json.dumps(payload)
    if is_postgres_enabled():
        try:
            ensure_pg_schema()
            with _get_pg_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO market_cache (cache_key, payload_json, cached_at)
                        VALUES (%s, %s::jsonb, NOW())
                        ON CONFLICT (cache_key) DO UPDATE
                        SET payload_json = EXCLUDED.payload_json, cached_at = NOW();
                        """,
                        (cache_key, payload_str),
                    )
        except Exception:
            pass
        return

    conn = _get_sqlite_conn()
    try:
        conn.execute(
            """
            INSERT INTO market_cache (cache_key, payload_json, cached_at)
            VALUES (?, ?, ?)
            ON CONFLICT (cache_key) DO UPDATE
            SET payload_json = excluded.payload_json, cached_at = excluded.cached_at;
            """,
            (cache_key, payload_str, time.time()),
        )
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()
