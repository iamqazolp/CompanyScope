import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import json
import os
import queue
import threading
from typing import Any, Optional

from fastapi import APIRouter, FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from src.agent import process_query
from src.config import (
    ADMIN_INGEST_KEY,
    APP_VERSION,
    CORS_ALLOW_ORIGINS,
    DAILY_QUERY_LIMIT,
    DEFAULT_TICKER,
    EMBEDDING_MODEL,
    INGEST_YEARS,
    LANGFUSE_PUBLIC_KEY,
    LANGFUSE_SECRET_KEY,
    LLM_PROVIDER,
    RATE_LIMIT_PER_MINUTE,
    TIER1_MODEL,
    TIER2_MODEL,
    get_langfuse,
    obs_context,
    propagate_trace_attributes,
)
from src.db import (
    consume_quota,
    get_quota_status,
    get_shared_report,
    is_postgres_enabled,
    make_guest_cookie,
    save_shared_report,
    verify_guest_cookie,
)
from src.embed import build_index, get_index_stats, is_cloud_vector_enabled
from src.embeddings import get_active_embedding_model_name
from src.ingest import ingest_company
from src.multi_agent import (
    classify_needed_specialists,
    detect_tickers,
    run_multi_agent_query,
)
from src.showcase import get_showcase_by_slug, list_showcase_summaries
from src.tools import get_company_financial_summary

GUEST_COOKIE_NAME = "cs_guest"


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    yield
    lf = get_langfuse()
    if lf is not None:
        try:
            lf.flush()
        except Exception:
            pass


limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="CompanyScope API",
    description="Zero-hallucination SEC filing, XBRL, earnings & sentiment analyst API",
    version=APP_VERSION,
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AskRequest(BaseModel):
    question: str
    ticker: Optional[str] = DEFAULT_TICKER
    tickers: Optional[list[str]] = None
    mode: Optional[str] = "single"
    history: Optional[list[dict[str, str]]] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    session_id: Optional[str] = None
    user_id: Optional[str] = None


class CompareRequest(BaseModel):
    question: str
    tickers: list[str]
    history: Optional[list[dict[str, str]]] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    session_id: Optional[str] = None
    user_id: Optional[str] = None


class IngestRequest(BaseModel):
    ticker: str
    years: Optional[list[int]] = None


def _extract_client_ip(request: Request) -> str:
    for header in ("x-vercel-forwarded-for", "x-forwarded-for", "x-real-ip"):
        val = request.headers.get(header)
        if val:
            return val.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "127.0.0.1"


def _resolve_guest_identity(request: Request) -> tuple[str, str, str | None]:
    """Returns (client_ip, guest_id, new_cookie_value_if_created)."""
    client_ip = _extract_client_ip(request)
    raw_cookie = request.cookies.get(GUEST_COOKIE_NAME)
    verified_id = verify_guest_cookie(raw_cookie)
    if verified_id:
        return client_ip, verified_id, None
    signed_cookie = make_guest_cookie()
    new_id = signed_cookie.split(".", 1)[0]
    return client_ip, new_id, signed_cookie


def _attach_guest_cookie(response: Response, new_cookie: str | None) -> None:
    if new_cookie:
        response.set_cookie(
            key=GUEST_COOKIE_NAME,
            value=new_cookie,
            max_age=60 * 60 * 24 * 365,
            httponly=True,
            samesite="lax",
            secure=bool(os.getenv("VERCEL")),
        )


def _should_enforce_quota() -> bool:
    if os.getenv("PYTEST_CURRENT_TEST"):
        return False
    return bool(getattr(app.state.limiter, "enabled", True))


def _execute_query_dispatch(
    payload: AskRequest,
    event_cb: Any = None,
) -> tuple[dict[str, Any], list[str], str]:
    target_ticker: str = (payload.ticker or DEFAULT_TICKER).upper().strip()
    mode = (payload.mode or "single").lower()
    explicit_tickers = [t.upper().strip() for t in (payload.tickers or []) if t.strip()]

    if mode in ("multi_agent", "multi"):
        resolved_tickers = detect_tickers(
            payload.question, target_ticker, explicit_tickers or None
        )
        res = run_multi_agent_query(
            question=payload.question,
            ticker=target_ticker,
            tickers=explicit_tickers or None,
            history=payload.history,
            provider=payload.provider,
            model=payload.model,
            session_id=payload.session_id,
            user_id=payload.user_id,
            event_cb=event_cb,
        )
        return res, resolved_tickers, "multi_agent"

    if mode == "auto":
        detected = detect_tickers(
            payload.question, target_ticker, explicit_tickers or None
        )
        needed_roles = classify_needed_specialists(payload.question)
        if len(detected) > 1 or explicit_tickers or len(needed_roles) > 1:
            res = run_multi_agent_query(
                question=payload.question,
                ticker=target_ticker,
                tickers=detected,
                history=payload.history,
                provider=payload.provider,
                model=payload.model,
                session_id=payload.session_id,
                user_id=payload.user_id,
                event_cb=event_cb,
            )
            return res, detected, "multi_agent"

    res = process_query(
        question=payload.question,
        ticker=target_ticker,
        history=payload.history,
        provider=payload.provider,
        model=payload.model,
        session_id=payload.session_id,
        user_id=payload.user_id,
        event_cb=event_cb,
    )
    return res, [target_ticker], "single"


router = APIRouter()


@router.get("/health")
def health_check() -> dict[str, Any]:
    cloud_vec = is_cloud_vector_enabled()
    return {
        "status": "ok",
        "version": APP_VERSION,
        "provider": LLM_PROVIDER,
        "model": TIER1_MODEL,
        "tier1_model": TIER1_MODEL,
        "tier2_model": TIER2_MODEL,
        "embedding_model": (
            get_active_embedding_model_name() if cloud_vec else EMBEDDING_MODEL
        ),
        "vector_backend": "pgvector" if cloud_vec else (
            "postgres" if is_postgres_enabled() else "local"
        ),
        "daily_query_limit": DAILY_QUERY_LIMIT,
        "langfuse_enabled": bool(LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY),
        "multi_agent_enabled": True,
    }


@router.get("/quota")
def quota_status(request: Request, response: Response) -> dict[str, Any]:
    client_ip, guest_id, new_cookie = _resolve_guest_identity(request)
    _attach_guest_cookie(response, new_cookie)
    return get_quota_status(client_ip, guest_id, daily_limit=DAILY_QUERY_LIMIT)


@router.get("/showcase")
def get_showcase_list() -> dict[str, Any]:
    return {"reports": list_showcase_summaries()}


@router.get("/reports/{slug}")
def fetch_report_by_slug(slug: str) -> dict[str, Any]:
    showcase = get_showcase_by_slug(slug)
    if showcase is not None:
        return showcase
    saved = get_shared_report(slug)
    if saved is not None:
        return saved
    raise HTTPException(status_code=404, detail="Report not found.")


@router.get("/tickers")
def list_indexed_tickers() -> dict[str, Any]:
    try:
        return get_index_stats()
    except Exception as e:
        return {"error": f"Failed to read index stats: {str(e)}"}


@router.post("/ingest")
def trigger_ingestion(
    payload: IngestRequest,
    x_admin_key: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    if ADMIN_INGEST_KEY and x_admin_key != ADMIN_INGEST_KEY:
        raise HTTPException(
            status_code=403,
            detail="Admin key required for cloud ingestion.",
        )

    target_ticker = payload.ticker.upper().strip()
    target_years = payload.years if payload.years else INGEST_YEARS
    lf = get_langfuse()
    active_emb = (
        get_active_embedding_model_name()
        if is_cloud_vector_enabled()
        else EMBEDDING_MODEL
    )

    with obs_context(
        lf,
        as_type="chain",
        name="ingest-company-filings",
        input={"ticker": target_ticker, "years": target_years},
        version=APP_VERSION,
    ) as root_obs:
        with propagate_trace_attributes(
            lf,
            tags=["company-scope", "ingestion", f"ticker:{target_ticker}"],
            version=APP_VERSION,
            trace_name="ingest-company-filings",
            metadata={"ticker": target_ticker},
        ):
            try:
                with obs_context(
                    lf,
                    as_type="span",
                    name="extract-and-chunk-filings",
                    input={"ticker": target_ticker, "years": target_years},
                ) as chunk_obs:
                    ingest_res = ingest_company(
                        ticker=target_ticker, years=target_years
                    )
                    if chunk_obs is not None:
                        try:
                            chunk_obs.update(output=ingest_res)
                        except Exception:
                            pass

                with obs_context(
                    lf,
                    as_type="embedding",
                    name="embed-and-index-chunks",
                    model=active_emb,
                    input={
                        "ticker": target_ticker,
                        "chunks_created": ingest_res.get("chunks_created", 0),
                    },
                ) as idx_obs:
                    indexed_count = build_index(ticker_filter=target_ticker)
                    if idx_obs is not None:
                        try:
                            idx_obs.update(output={"chunks_indexed": indexed_count})
                        except Exception:
                            pass

                ingest_res["chunks_indexed"] = indexed_count
                if root_obs is not None:
                    try:
                        root_obs.update(output=ingest_res)
                    except Exception:
                        pass
                if lf is not None:
                    try:
                        lf.flush()
                    except Exception:
                        pass
                return ingest_res
            except Exception as e:
                err_out = {"error": f"Ingestion failed: {str(e)}"}
                if root_obs is not None:
                    try:
                        root_obs.update(
                            output=err_out,
                            level="ERROR",
                            status_message=str(e),
                        )
                    except Exception:
                        pass
                if lf is not None:
                    try:
                        lf.flush()
                    except Exception:
                        pass
                return err_out


@router.get("/financials/{ticker}")
def get_ticker_financials(ticker: str) -> dict[str, Any]:
    try:
        clean_ticker = ticker.upper().strip()
        rows = get_company_financial_summary(clean_ticker)
        return {"ticker": clean_ticker, "financials": rows}
    except Exception as e:
        return {"error": f"Failed to fetch financial summary: {str(e)}"}


@router.post("/compare")
@limiter.limit(f"{RATE_LIMIT_PER_MINUTE}/minute")
def compare_companies(
    request: Request, response: Response, payload: CompareRequest
) -> Any:
    client_ip, guest_id, new_cookie = _resolve_guest_identity(request)
    _attach_guest_cookie(response, new_cookie)

    quota_info: dict[str, Any] | None = None
    if _should_enforce_quota():
        allowed, quota_info = consume_quota(
            client_ip, guest_id, daily_limit=DAILY_QUERY_LIMIT
        )
        if not allowed:
            err_resp = JSONResponse(
                status_code=429,
                content={
                    "error": f"Daily free limit reached ({DAILY_QUERY_LIMIT} queries/day). Explore Showcase Reports or check back after UTC midnight.",
                    "quota": quota_info,
                },
            )
            _attach_guest_cookie(err_resp, new_cookie)
            return err_resp

    try:
        primary = payload.tickers[0] if payload.tickers else DEFAULT_TICKER
        result = run_multi_agent_query(
            question=payload.question,
            ticker=primary,
            tickers=payload.tickers,
            history=payload.history,
            provider=payload.provider,
            model=payload.model,
            session_id=payload.session_id,
            user_id=payload.user_id,
        )
        if "error" not in result:
            slug = save_shared_report(
                question=payload.question,
                tickers=[t.upper() for t in payload.tickers],
                mode="multi_agent",
                payload=result,
            )
            result["report_slug"] = slug
        if quota_info is not None:
            result["quota"] = quota_info
        return result
    except Exception as e:
        return {"error": f"Multi-agent comparison error: {str(e)}"}


@router.post("/ask")
@limiter.limit(f"{RATE_LIMIT_PER_MINUTE}/minute")
def ask_question(
    request: Request, response: Response, payload: AskRequest
) -> Any:
    client_ip, guest_id, new_cookie = _resolve_guest_identity(request)
    _attach_guest_cookie(response, new_cookie)

    quota_info: dict[str, Any] | None = None
    if _should_enforce_quota():
        allowed, quota_info = consume_quota(
            client_ip, guest_id, daily_limit=DAILY_QUERY_LIMIT
        )
        if not allowed:
            err_resp = JSONResponse(
                status_code=429,
                content={
                    "error": f"Daily free limit reached ({DAILY_QUERY_LIMIT} queries/day). Explore Showcase Reports or check back after UTC midnight.",
                    "quota": quota_info,
                },
            )
            _attach_guest_cookie(err_resp, new_cookie)
            return err_resp

    try:
        result, resolved_tickers, resolved_mode = _execute_query_dispatch(payload)
        if "error" not in result:
            slug = save_shared_report(
                question=payload.question,
                tickers=resolved_tickers,
                mode=resolved_mode,
                payload=result,
            )
            result["report_slug"] = slug
        if quota_info is not None:
            result["quota"] = quota_info
        return result
    except Exception as e:
        return {"error": f"Internal server error: {str(e)}"}


@router.post("/ask/stream")
@limiter.limit(f"{RATE_LIMIT_PER_MINUTE}/minute")
async def ask_question_stream(request: Request, payload: AskRequest) -> Response:
    """
    Streams real-time multi-agent / single-agent execution events via Server-Sent Events (SSE),
    enforces the 5-queries/day guest quota without login, and persists a shareable report slug.
    """
    client_ip, guest_id, new_cookie = _resolve_guest_identity(request)

    quota_info: dict[str, Any] = get_quota_status(
        client_ip, guest_id, daily_limit=DAILY_QUERY_LIMIT
    )
    if _should_enforce_quota():
        allowed, quota_info = consume_quota(
            client_ip, guest_id, daily_limit=DAILY_QUERY_LIMIT
        )
        if not allowed:
            err_resp = JSONResponse(
                status_code=429,
                content={
                    "error": f"Daily free limit reached ({DAILY_QUERY_LIMIT} queries/day). Explore instant Showcase Reports above or return after UTC reset.",
                    "quota": quota_info,
                },
            )
            _attach_guest_cookie(err_resp, new_cookie)
            return err_resp

    ev_queue: queue.Queue[dict[str, Any] | None] = queue.Queue()

    def push_event(ev: dict[str, Any]) -> None:
        ev_queue.put(ev)

    def worker() -> None:
        try:
            result, resolved_tickers, resolved_mode = _execute_query_dispatch(
                payload, event_cb=push_event
            )
            slug: str | None = None
            if "error" not in result:
                slug = save_shared_report(
                    question=payload.question,
                    tickers=resolved_tickers,
                    mode=resolved_mode,
                    payload=result,
                )
                result["report_slug"] = slug
            result["quota"] = quota_info
            ev_queue.put(
                {
                    "type": "result",
                    "data": result,
                    "report_slug": slug,
                    "quota": quota_info,
                }
            )
        except Exception as exc:
            ev_queue.put(
                {
                    "type": "error",
                    "error": f"Execution error: {str(exc)}",
                    "quota": quota_info,
                }
            )
        finally:
            ev_queue.put(None)

    threading.Thread(target=worker, daemon=True).start()

    async def sse_generator() -> AsyncIterator[str]:
        yield f"data: {json.dumps({'type': 'quota', 'quota': quota_info})}\n\n"
        while True:
            try:
                item = ev_queue.get_nowait()
                if item is None:
                    yield "data: [DONE]\n\n"
                    break
                yield f"data: {json.dumps(item)}\n\n"
            except queue.Empty:
                await asyncio.sleep(0.06)

    stream_resp = StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
    _attach_guest_cookie(stream_resp, new_cookie)
    return stream_resp


# Mount at both root ("") for existing clients/tests and "/api" for Vercel Serverless routing
app.include_router(router)
app.include_router(router, prefix="/api")
