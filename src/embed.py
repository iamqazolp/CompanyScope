import json
from typing import Any

import chromadb
from sentence_transformers import SentenceTransformer

from src.config import (
    CHROMA_PATH,
    CHUNKS_FILE,
    COLLECTION_NAME,
    EMBEDDING_DEVICE,
    EMBEDDING_MODEL,
)

_client: chromadb.ClientAPI | None = None
_embedding_model: SentenceTransformer | None = None


def get_embedding_model() -> SentenceTransformer:
    """Returns a cached singleton SentenceTransformer model."""
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = SentenceTransformer(
            EMBEDDING_MODEL, device=EMBEDDING_DEVICE
        )
    return _embedding_model


def get_collection() -> Any:
    """Returns the ChromaDB collection object for querying."""
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    collection = _client.get_or_create_collection(name=COLLECTION_NAME)
    return collection


def build_index(ticker_filter: str | None = None) -> int:
    """Loads chunks, creates embeddings, and stores them in ChromaDB."""
    if not CHUNKS_FILE.exists():
        print(f"Chunks file {CHUNKS_FILE} not found. Run ingestion first.")
        return 0

    model = get_embedding_model()
    collection = get_collection()

    documents: list[str] = []
    metadatas: list[dict[str, Any]] = []
    ids: list[str] = []
    seen_ids: dict[str, int] = {}

    print("Loading chunks...")
    with open(CHUNKS_FILE, "r", encoding="utf-8") as f:
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

            documents.append(chunk["text"])
            metadatas.append(
                {
                    "ticker": str(chunk["ticker"]).upper(),
                    "year": int(chunk["year"]),
                    "filing_type": str(chunk["filing_type"]),
                    "section": str(chunk["section"]),
                    "chunk_id": base_id,
                    "chunk_level": str(chunk.get("chunk_level", "leaf")),
                }
            )
            ids.append(unique_id)

    if not documents:
        print("No documents to index.")
        return 0

    print(f"Creating embeddings for {len(documents)} chunks...")
    embeddings = model.encode(documents, show_progress_bar=True).tolist()

    print("Storing in ChromaDB...")
    batch_size = 5000
    for i in range(0, len(ids), batch_size):
        collection.upsert(
            ids=ids[i : i + batch_size],
            documents=documents[i : i + batch_size],
            metadatas=metadatas[i : i + batch_size],
            embeddings=embeddings[i : i + batch_size],
        )

    return len(ids)


def get_index_stats() -> dict[str, Any]:
    """Returns summary statistics of tickers, years, and chunk counts in ChromaDB."""
    collection = get_collection()
    total = collection.count()
    if total == 0:
        return {"total_chunks": 0, "tickers": {}}

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
    return {"total_chunks": total, "tickers": formatted_tickers}


if __name__ == "__main__":
    num_chunks = build_index()
    print(f"Index built with {num_chunks} chunks.")
