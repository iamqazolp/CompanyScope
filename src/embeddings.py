import math
import time
from typing import Any

import requests

from src.config import (
    GEMINI_API_KEY,
    GEMINI_EMBEDDING_DIM,
    GEMINI_EMBEDDING_MODEL,
)

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
_FALLBACK_MODELS = [
    GEMINI_EMBEDDING_MODEL,
    "gemini-embedding-2-preview",
    "gemini-embedding-001",
]

_resolved_model: str | None = None


def is_cloud_embedding_enabled() -> bool:
    """Returns True when a Gemini API key is configured for cloud embeddings."""
    return bool(GEMINI_API_KEY)


def _normalize_vec(values: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in values))
    if norm <= 0.0:
        return values
    return [v / norm for v in values]


def _candidate_models() -> list[str]:
    if _resolved_model:
        return [_resolved_model]
    seen: list[str] = []
    for m in _FALLBACK_MODELS:
        clean = m.replace("models/", "").strip()
        if clean and clean not in seen:
            seen.append(clean)
    return seen


def embed_query_cloud(
    query: str,
    task_type: str = "RETRIEVAL_QUERY",
    output_dim: int = GEMINI_EMBEDDING_DIM,
) -> list[float]:
    """Embeds a single search query via Google Gemini Embedding 2 REST API."""
    global _resolved_model
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not configured.")

    headers = {
        "x-goog-api-key": GEMINI_API_KEY,
        "Content-Type": "application/json",
    }

    last_err = ""
    for model_id in _candidate_models():
        url = f"{GEMINI_API_BASE}/models/{model_id}:embedContent"
        payload: dict[str, Any] = {
            "model": f"models/{model_id}",
            "content": {"parts": [{"text": query or " "}]},
            "taskType": task_type,
            "outputDimensionality": output_dim,
        }
        for attempt in range(3):
            resp = requests.post(url, headers=headers, json=payload, timeout=25)
            if resp.status_code == 404:
                last_err = f"Model {model_id} returned 404"
                break
            if resp.status_code == 429 and attempt < 2:
                time.sleep(1.5 * (attempt + 1))
                continue
            if not resp.ok:
                # Retry once without taskType if preview endpoint rejects taskType
                if resp.status_code == 400 and "taskType" in payload:
                    payload.pop("taskType", None)
                    continue
                raise RuntimeError(
                    f"Gemini embedContent error ({resp.status_code}): {resp.text[:300]}"
                )
            data = resp.json() or {}
            values = ((data.get("embedding") or {}).get("values")) or []
            if not values:
                raise RuntimeError("Gemini embedContent returned empty embedding.")
            _resolved_model = model_id
            return _normalize_vec([float(x) for x in values])

    raise RuntimeError(f"All Gemini embedding model candidates failed: {last_err}")


def embed_texts_cloud(
    texts: list[str],
    task_type: str = "RETRIEVAL_DOCUMENT",
    output_dim: int = GEMINI_EMBEDDING_DIM,
    batch_size: int = 80,
) -> list[list[float]]:
    """Batch-embeds document chunks via Google Gemini Embedding 2 (:batchEmbedContents)."""
    global _resolved_model
    if not texts:
        return []
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not configured.")

    headers = {
        "x-goog-api-key": GEMINI_API_KEY,
        "Content-Type": "application/json",
    }

    all_vectors: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        batch_done = False
        last_err = ""

        for model_id in _candidate_models():
            url = f"{GEMINI_API_BASE}/models/{model_id}:batchEmbedContents"
            use_task_type = True
            for attempt in range(3):
                reqs: list[dict[str, Any]] = []
                for txt in batch:
                    item: dict[str, Any] = {
                        "model": f"models/{model_id}",
                        "content": {"parts": [{"text": txt[:18000] or " "}]},
                        "outputDimensionality": output_dim,
                    }
                    if use_task_type:
                        item["taskType"] = task_type
                    reqs.append(item)

                resp = requests.post(
                    url, headers=headers, json={"requests": reqs}, timeout=45
                )
                if resp.status_code == 404:
                    last_err = f"Model {model_id} returned 404"
                    break
                if resp.status_code == 429 and attempt < 2:
                    time.sleep(2.0 * (attempt + 1))
                    continue
                if resp.status_code == 400 and use_task_type:
                    use_task_type = False
                    continue
                if not resp.ok:
                    raise RuntimeError(
                        f"Gemini batchEmbedContents error ({resp.status_code}): {resp.text[:300]}"
                    )

                data = resp.json() or {}
                emb_list = data.get("embeddings") or []
                if len(emb_list) != len(batch):
                    raise RuntimeError(
                        f"Expected {len(batch)} embeddings, received {len(emb_list)}."
                    )
                _resolved_model = model_id
                for emb_obj in emb_list:
                    vals = [float(x) for x in (emb_obj.get("values") or [])]
                    all_vectors.append(_normalize_vec(vals))
                batch_done = True
                break

            if batch_done:
                break

        if not batch_done:
            raise RuntimeError(
                f"Gemini batch embedding failed across candidate models: {last_err}"
            )

    return all_vectors


def get_active_embedding_model_name() -> str:
    """Returns the resolved cloud model name or configured default."""
    return _resolved_model or GEMINI_EMBEDDING_MODEL
