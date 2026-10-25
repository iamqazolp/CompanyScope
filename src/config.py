from contextlib import nullcontext
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

APP_VERSION = os.getenv("APP_VERSION", "0.2.0")


def _get_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _get_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _get_list(name: str, default: str) -> list[str]:
    value = os.getenv(name, default)
    return [item.strip() for item in value.split(",") if item.strip()]


def _resolve_path(name: str, default: Path) -> Path:
    value = os.getenv(name)
    if value is None:
        return default
    path = Path(value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


# LLM Provider Configuration
OPENAI_URL = os.getenv("OPENAI_URL", "https://api.shopaikey.com").rstrip("/")
OPENAI_KEY = os.getenv("OPENAI_KEY", os.getenv("OPENAI_API_KEY", ""))
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-6-luna")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_TIMEOUT = _get_float("GROQ_TIMEOUT", 30.0)

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai" if OPENAI_KEY else "groq").lower()
LLM_TIMEOUT = _get_float("LLM_TIMEOUT", 90.0)

# SEC EDGAR Configuration
EDGAR_IDENTITY = (
    os.getenv("EDGAR_IDENTITY") or "CompanyScope TestBot contact@example.com"
)
DEFAULT_TICKER = os.getenv("DEFAULT_TICKER", "AAPL")

# Embedding & Vector Store Configuration
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
EMBEDDING_DEVICE = os.getenv("EMBEDDING_DEVICE", "cpu")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "narratives")
CHROMA_PATH = _resolve_path("CHROMA_PATH", PROJECT_ROOT / "chroma_db")
CHUNKS_FILE = _resolve_path(
    "CHUNKS_FILE", PROJECT_ROOT / "data" / "processed" / "chunks.jsonl"
)
RAW_DIR = _resolve_path("RAW_DIR", PROJECT_ROOT / "data" / "raw")
PROCESSED_DIR = _resolve_path("PROCESSED_DIR", PROJECT_ROOT / "data" / "processed")
SEARCH_RESULTS_LIMIT = _get_int("SEARCH_RESULTS_LIMIT", 4)
CHUNK_SIZE = _get_int("CHUNK_SIZE", 500)
CHUNK_OVERLAP = _get_int("CHUNK_OVERLAP", 50)

# API & Rate Limiting Configuration
RATE_LIMIT_PER_MINUTE = _get_int("RATE_LIMIT_PER_MINUTE", 10)
CORS_ALLOW_ORIGINS = _get_list("CORS_ALLOW_ORIGINS", "*")

# Ingestion Defaults
INGEST_TICKER = os.getenv("INGEST_TICKER", DEFAULT_TICKER)
INGEST_YEARS = [
    int(item.strip())
    for item in os.getenv("INGEST_YEARS", "2020,2021,2022,2023,2024,2025,2026").split(
        ","
    )
    if item.strip()
]

# Observability (Langfuse)
LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY", "")
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY", "")
LANGFUSE_HOST = os.getenv(
    "LANGFUSE_HOST", os.getenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com")
)

# GPT-6-Luna Pricing (USD per 1M tokens)
GPT6_LUNA_INPUT_PRICE_PER_1M = _get_float("GPT6_LUNA_INPUT_PRICE_PER_1M", 0.10)
GPT6_LUNA_CACHED_INPUT_PRICE_PER_1M = _get_float(
    "GPT6_LUNA_CACHED_INPUT_PRICE_PER_1M", 0.01
)
GPT6_LUNA_CACHE_WRITE_PRICE_PER_1M = _get_float(
    "GPT6_LUNA_CACHE_WRITE_PRICE_PER_1M", 0.125
)
GPT6_LUNA_OUTPUT_PRICE_PER_1M = _get_float("GPT6_LUNA_OUTPUT_PRICE_PER_1M", 0.50)

LANGFUSE_TRACING_ENVIRONMENT = os.getenv(
    "LANGFUSE_TRACING_ENVIRONMENT",
    os.getenv("LANGFUSE_ENVIRONMENT", "development"),
)

_langfuse_client: Any = None


def get_langfuse() -> Any:
    """Initializes the Langfuse v4 client singleton after environment variables are loaded."""
    global _langfuse_client
    if _langfuse_client is False:
        return None
    if _langfuse_client is not None:
        return _langfuse_client
    if LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY:
        try:
            from langfuse import Langfuse

            _langfuse_client = Langfuse(
                public_key=LANGFUSE_PUBLIC_KEY,
                secret_key=LANGFUSE_SECRET_KEY,
                host=LANGFUSE_HOST,
                environment=LANGFUSE_TRACING_ENVIRONMENT,
                release=APP_VERSION,
            )
            return _langfuse_client
        except Exception:
            _langfuse_client = False
            return None
    _langfuse_client = False
    return None


def obs_context(lf: Any, **kwargs: Any) -> Any:
    """Returns a Langfuse start_as_current_observation context manager if enabled, else nullcontext."""
    if lf is not None:
        try:
            return lf.start_as_current_observation(**kwargs)
        except Exception:
            return nullcontext(None)
    return nullcontext(None)


def propagate_trace_attributes(lf: Any, **kwargs: Any) -> Any:
    """Propagates trace-level attributes (session_id, user_id, tags, version, metadata, trace_name) to child observations."""
    if lf is not None:
        try:
            from langfuse import propagate_attributes

            return propagate_attributes(**kwargs)
        except Exception:
            return nullcontext(None)
    return nullcontext(None)
