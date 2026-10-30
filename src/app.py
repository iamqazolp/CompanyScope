from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from src.agent import process_query
from src.config import (
    APP_VERSION,
    CORS_ALLOW_ORIGINS,
    DEFAULT_TICKER,
    EMBEDDING_MODEL,
    INGEST_YEARS,
    LANGFUSE_PUBLIC_KEY,
    LANGFUSE_SECRET_KEY,
    LLM_PROVIDER,
    OPENAI_MODEL,
    RATE_LIMIT_PER_MINUTE,
    get_langfuse,
    obs_context,
    propagate_trace_attributes,
)
from src.embed import build_index, get_index_stats
from src.ingest import ingest_company
from src.multi_agent import detect_tickers, run_multi_agent_query
from src.tools import get_company_financial_summary


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
    description="Zero-hallucination SEC filing & XBRL financial analysis agent (Single & Multi-Agent)",
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


@app.get("/health")
def health_check() -> dict[str, Any]:
    return {
        "status": "ok",
        "provider": LLM_PROVIDER,
        "model": OPENAI_MODEL,
        "langfuse_enabled": bool(LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY),
        "multi_agent_enabled": True,
    }


@app.get("/tickers")
def list_indexed_tickers() -> dict[str, Any]:
    try:
        return get_index_stats()
    except Exception as e:
        return {"error": f"Failed to read index stats: {str(e)}"}


@app.post("/ingest")
def trigger_ingestion(payload: IngestRequest) -> dict[str, Any]:
    target_ticker = payload.ticker.upper().strip()
    target_years = payload.years if payload.years else INGEST_YEARS
    lf = get_langfuse()

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
                    model=EMBEDDING_MODEL,
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


@app.get("/financials/{ticker}")
def get_ticker_financials(ticker: str) -> dict[str, Any]:
    try:
        clean_ticker = ticker.upper().strip()
        rows = get_company_financial_summary(clean_ticker)
        return {"ticker": clean_ticker, "financials": rows}
    except Exception as e:
        return {"error": f"Failed to fetch financial summary: {str(e)}"}


@app.post("/compare")
@limiter.limit(f"{RATE_LIMIT_PER_MINUTE}/minute")
def compare_companies(request: Request, payload: CompareRequest) -> dict[str, Any]:
    try:
        primary = payload.tickers[0] if payload.tickers else DEFAULT_TICKER
        return run_multi_agent_query(
            question=payload.question,
            ticker=primary,
            tickers=payload.tickers,
            history=payload.history,
            provider=payload.provider,
            model=payload.model,
            session_id=payload.session_id,
            user_id=payload.user_id,
        )
    except Exception as e:
        return {"error": f"Multi-agent comparison error: {str(e)}"}


@app.post("/ask")
@limiter.limit(f"{RATE_LIMIT_PER_MINUTE}/minute")
def ask_question(request: Request, payload: AskRequest) -> dict[str, Any]:
    try:
        target_ticker: str = payload.ticker if payload.ticker else DEFAULT_TICKER
        mode = (payload.mode or "single").lower()

        if mode == "multi_agent":
            return run_multi_agent_query(
                question=payload.question,
                ticker=target_ticker,
                tickers=payload.tickers,
                history=payload.history,
                provider=payload.provider,
                model=payload.model,
                session_id=payload.session_id,
                user_id=payload.user_id,
            )
        if mode == "auto":
            detected = detect_tickers(
                payload.question, target_ticker, payload.tickers
            )
            if len(detected) > 1:
                return run_multi_agent_query(
                    question=payload.question,
                    ticker=target_ticker,
                    tickers=detected,
                    history=payload.history,
                    provider=payload.provider,
                    model=payload.model,
                    session_id=payload.session_id,
                    user_id=payload.user_id,
                )

        result = process_query(
            question=payload.question,
            ticker=target_ticker,
            history=payload.history,
            provider=payload.provider,
            model=payload.model,
            session_id=payload.session_id,
            user_id=payload.user_id,
        )
        return result
    except Exception as e:
        return {"error": f"Internal server error: {str(e)}"}
