from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import os
from dotenv import load_dotenv

load_dotenv()

from src.agent import process_query

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(title="CompanyScope API")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ALLOW_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AskRequest(BaseModel):
    question: str
    ticker: Optional[str] = os.getenv("DEFAULT_TICKER", "AAPL")


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/ask")
@limiter.limit(f"{os.getenv('RATE_LIMIT_PER_MINUTE', 10)}/minute")
def ask_question(request: Request, payload: AskRequest):
    try:
        result = process_query(
            question=payload.question, ticker=payload.ticker or os.getenv("DEFAULT_TICKER", "AAPL")
        )
        return result
    except Exception as e:
        return {"error": f"Internal server error: {str(e)}"}
