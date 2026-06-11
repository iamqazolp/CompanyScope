import json
from pathlib import Path
import chromadb
from sentence_transformers import SentenceTransformer

CHUNKS_FILE = Path("data/processed/chunks.jsonl")
CHROMA_PATH = "./chroma_db"
COLLECTION_NAME = "narratives"
MODEL_NAME = "all-MiniLM-L6-v2"

def get_collection():
    """Returns the ChromaDB collection object for querying."""
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    collection = client.get_or_create_collection(name=COLLECTION_NAME)
    return collection

def build_index():
    """Loads chunks, creates embeddings, and stores them in ChromaDB."""
    if not CHUNKS_FILE.exists():
        print(f"Chunks file {CHUNKS_FILE} not found. Run ingestion first.")
        return 0

    print("Loading model...")
    model = SentenceTransformer(MODEL_NAME, device='cpu')
    
    collection = get_collection()
    
    documents = []
    metadatas = []
    ids = []
    
    print("Loading chunks...")
    with open(CHUNKS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            chunk = json.loads(line)
            documents.append(chunk["text"])
            
            metadata = {
                "ticker": chunk["ticker"],
                "year": chunk["year"],
                "filing_type": chunk["filing_type"],
                "section": chunk["section"],
                "chunk_id": chunk["chunk_id"]
            }
            metadatas.append(metadata)
            unique_id = f"{chunk['chunk_id']}_{len(ids)}"
            ids.append(unique_id)            
    if not documents:
        print("No documents to index.")
        return 0
        
    print(f"Creating embeddings for {len(documents)} chunks...")
    # sentence-transformers will compute embeddings using the specified model
    embeddings = model.encode(documents, show_progress_bar=True).tolist()
    
    print("Storing in ChromaDB...")
    # Use upsert to avoid errors if run multiple times
    batch_size = 5000
    for i in range(0, len(ids), batch_size):
        collection.upsert(
            ids=ids[i:i + batch_size],
            documents=documents[i:i + batch_size],
            metadatas=metadatas[i:i + batch_size],
            embeddings=embeddings[i:i + batch_size]
        )
        
    return len(ids)

if __name__ == "__main__":
    num_chunks = build_index()
    print(f"Index built with {num_chunks} chunks.")
