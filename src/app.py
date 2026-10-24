from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from src.agent import process_query
from src.config import (
    CORS_ALLOW_ORIGINS,
    DEFAULT_TICKER,
    GROQ_MODEL,
    INGEST_YEARS,
    LANGFUSE_PUBLIC_KEY,
    LANGFUSE_SECRET_KEY,
    LLM_PROVIDER,
    OPENAI_MODEL,
    RATE_LIMIT_PER_MINUTE,
)
from src.embed import build_index, get_index_stats
from src.ingest import ingest_company
from src.tools import get_company_financial_summary

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="CompanyScope API",
    description="Zero-hallucination SEC filing & XBRL financial analysis agent",
    version="0.2.0",
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
    history: Optional[list[dict[str, str]]] = None
    provider: Optional[str] = None
    model: Optional[str] = None


class IngestRequest(BaseModel):
    ticker: str
    years: Optional[list[int]] = None


@app.get("/health")
def health_check() -> dict[str, Any]:
    active_model = OPENAI_MODEL if LLM_PROVIDER == "openai" else GROQ_MODEL
    return {
        "status": "ok",
        "provider": LLM_PROVIDER,
        "model": active_model,
        "langfuse_enabled": bool(LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY),
    }


@app.get("/tickers")
def list_indexed_tickers() -> dict[str, Any]:
    try:
        return get_index_stats()
    except Exception as e:
        return {"error": f"Failed to read index stats: {str(e)}"}


@app.post("/ingest")
def trigger_ingestion(payload: IngestRequest) -> dict[str, Any]:
    try:
        target_ticker = payload.ticker.upper().strip()
        target_years = payload.years if payload.years else INGEST_YEARS
        ingest_res = ingest_company(ticker=target_ticker, years=target_years)
        indexed_count = build_index(ticker_filter=target_ticker)
        ingest_res["chunks_indexed"] = indexed_count
        return ingest_res
    except Exception as e:
        return {"error": f"Ingestion failed: {str(e)}"}


@app.get("/financials/{ticker}")
def get_ticker_financials(ticker: str) -> dict[str, Any]:
    try:
        clean_ticker = ticker.upper().strip()
        rows = get_company_financial_summary(clean_ticker)
        return {"ticker": clean_ticker, "financials": rows}
    except Exception as e:
        return {"error": f"Failed to fetch financial summary: {str(e)}"}


@app.post("/ask")
@limiter.limit(f"{RATE_LIMIT_PER_MINUTE}/minute")
def ask_question(request: Request, payload: AskRequest) -> dict[str, Any]:
    try:
        target_ticker: str = payload.ticker if payload.ticker else DEFAULT_TICKER
        result = process_query(
            question=payload.question,
            ticker=target_ticker,
            history=payload.history,
            provider=payload.provider,
            model=payload.model,
        )
        return result
    except Exception as e:
        return {"error": f"Internal server error: {str(e)}"}
