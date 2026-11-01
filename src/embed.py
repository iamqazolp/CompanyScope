import json
from typing import Any

from src.config import (
    BUNDLED_CHUNKS_FILE,
    CHROMA_PATH,
    CHUNKS_FILE,
    COLLECTION_NAME,
    EMBEDDING_DEVICE,
    EMBEDDING_MODEL,
)
from src.db import (
    get_index_stats_pg,
    is_postgres_enabled,
    upsert_chunks_pg,
)
from src.embeddings import (
    embed_texts_cloud,
    get_active_embedding_model_name,
    is_cloud_embedding_enabled,
)

_client: Any = None
_embedding_model: Any = None


def is_cloud_vector_enabled() -> bool:
    """Returns True when both cloud Postgres (pgvector) and Gemini Embedding 2 are configured."""
    return is_postgres_enabled() and is_cloud_embedding_enabled()


def is_local_chroma_available() -> bool:
    """Checks whether local chromadb + sentence_transformers are installed."""
    try:
        import chromadb as _c  # noqa: F401
        import sentence_transformers as _st  # noqa: F401

        return True
    except Exception:
        return False


def get_embedding_model() -> Any:
    """Returns a cached singleton SentenceTransformer model for local dev."""
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer

        _embedding_model = SentenceTransformer(
            EMBEDDING_MODEL, device=EMBEDDING_DEVICE
        )
    return _embedding_model


def get_collection() -> Any:
    """Returns the local ChromaDB collection object for querying."""
    global _client
    if _client is None:
        import chromadb

        _client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    return _client.get_or_create_collection(name=COLLECTION_NAME)


def _load_chunks_from_jsonl(ticker_filter: str | None = None) -> list[dict[str, Any]]:
    candidate_files = [CHUNKS_FILE]
    if BUNDLED_CHUNKS_FILE != CHUNKS_FILE and BUNDLED_CHUNKS_FILE.exists():
        candidate_files.insert(0, BUNDLED_CHUNKS_FILE)

    rows_by_id: dict[str, dict[str, Any]] = {}
    seen_ids: dict[str, int] = {}

    for fpath in candidate_files:
        if not fpath.exists():
            continue
        with open(fpath, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                chunk = json.loads(line)
                if ticker_filter and chunk.get("ticker", "").upper() != ticker_filter.upper():
                    continue
                base_id = str(chunk["chunk_id"])
                count = seen_ids.get(base_id, 0)
                seen_ids[base_id] = count + 1
                unique_id = base_id if count == 0 else f"{base_id}_{count}"
                rows_by_id[unique_id] = {
                    "id": unique_id,
                    "chunk_id": base_id,
                    "ticker": str(chunk["ticker"]).upper(),
                    "year": int(chunk["year"]),
                    "filing_type": str(chunk["filing_type"]),
                    "section": str(chunk["section"]),
                    "chunk_level": str(chunk.get("chunk_level", "leaf")),
                    "chunk_text": str(chunk["text"]),
                }
    return list(rows_by_id.values())


def build_index(ticker_filter: str | None = None) -> int:
    """
    Loads processed chunks, computes embeddings, and indexes into:
    - Cloud Postgres (pgvector) via Gemini Embedding 2 when DATABASE_URL + GEMINI_API_KEY are set
    - Local ChromaDB via SentenceTransformers otherwise.
    """
    rows = _load_chunks_from_jsonl(ticker_filter=ticker_filter)
    if not rows:
        print(f"No chunks found in {CHUNKS_FILE}. Run ingestion first.")
        return 0

    documents = [r["chunk_text"] for r in rows]

    if is_cloud_vector_enabled():
        model_name = get_active_embedding_model_name()
        print(
            f"Creating cloud embeddings ({model_name}) for {len(documents)} chunks..."
        )
        embeddings = embed_texts_cloud(documents, task_type="RETRIEVAL_DOCUMENT")
        print("Upserting chunks into cloud Postgres (pgvector)...")
        return upsert_chunks_pg(rows, embeddings, ticker_filter=ticker_filter)

    if not is_local_chroma_available():
        raise RuntimeError(
            "Neither cloud vector config (DATABASE_URL + GEMINI_API_KEY) nor local chromadb/sentence-transformers is available."
        )

    model = get_embedding_model()
    collection = get_collection()
    ids = [r["id"] for r in rows]
    metadatas = [
        {
            "ticker": r["ticker"],
            "year": r["year"],
            "filing_type": r["filing_type"],
            "section": r["section"],
            "chunk_id": r["chunk_id"],
            "chunk_level": r["chunk_level"],
        }
        for r in rows
    ]

    print(f"Creating local embeddings for {len(documents)} chunks...")
    embeddings_local = model.encode(documents, show_progress_bar=True).tolist()

    print("Storing in ChromaDB...")
    try:
        if ticker_filter:
            collection.delete(where={"ticker": ticker_filter.upper()})
        else:
            existing = collection.get(include=[])
            if existing and existing.get("ids"):
                collection.delete(ids=existing["ids"])
    except Exception:
        pass

    batch_size = 5000
    for i in range(0, len(ids), batch_size):
        collection.upsert(
            ids=ids[i : i + batch_size],
            documents=documents[i : i + batch_size],
            metadatas=metadatas[i : i + batch_size],
            embeddings=embeddings_local[i : i + batch_size],
        )

    return len(ids)


def _get_jsonl_stats() -> dict[str, Any]:
    rows = _load_chunks_from_jsonl()
    tickers: dict[str, dict[str, Any]] = {}
    for r in rows:
        t = r["ticker"]
        if t not in tickers:
            tickers[t] = {"chunks": 0, "years": set(), "sections": set()}
        tickers[t]["chunks"] += 1
        tickers[t]["years"].add(int(r["year"]))
        tickers[t]["sections"].add(str(r["section"]))
    formatted = {
        t: {
            "chunks": info["chunks"],
            "years": sorted(list(info["years"])),
            "sections": sorted(list(info["sections"])),
        }
        for t, info in sorted(tickers.items())
    }
    return {"total_chunks": len(rows), "tickers": formatted, "backend": "jsonl_bm25"}


def get_index_stats() -> dict[str, Any]:
    """Returns summary statistics of tickers, years, and chunk counts in the active index."""
    if is_cloud_vector_enabled():
        try:
            pg_stats = get_index_stats_pg()
            if pg_stats.get("total_chunks", 0) > 0:
                return pg_stats
        except Exception:
            pass

    if is_local_chroma_available():
        try:
            collection = get_collection()
            total = collection.count()
            if total > 0:
                data = collection.get(include=["metadatas"])
                metadatas = data.get("metadatas") or []
                tickers: dict[str, dict[str, Any]] = {}
                for meta in metadatas:
                    if not meta:
                        continue
                    t = str(meta.get("ticker", "UNKNOWN")).upper()
                    y = meta.get("year")
                    sec = meta.get("section")
                    if t not in tickers:
                        tickers[t] = {"chunks": 0, "years": set(), "sections": set()}
                    tickers[t]["chunks"] += 1
                    if y is not None:
                        tickers[t]["years"].add(int(y))
                    if sec:
                        tickers[t]["sections"].add(str(sec))
                formatted_tickers = {
                    t: {
                        "chunks": info["chunks"],
                        "years": sorted(list(info["years"])),
                        "sections": sorted(list(info["sections"])),
                    }
                    for t, info in sorted(tickers.items())
                }
                return {
                    "total_chunks": total,
                    "tickers": formatted_tickers,
                    "backend": "chromadb",
                }
        except Exception:
            pass

    return _get_jsonl_stats()


if __name__ == "__main__":
    num_chunks = build_index()
    print(f"Index built with {num_chunks} chunks.")
