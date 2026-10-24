import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


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
