import chromadb
from chromadb.config import Settings as ChromaSettings
from app.config import settings

_client = None


def client():
    global _client
    if _client is None:
        _client = chromadb.HttpClient(
            host=settings.CHROMA_HOST,
            port=settings.CHROMA_PORT,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
    return _client


def collection_for_user(user_id: int):
    name = f"user_{user_id}"
    return client().get_or_create_collection(name=name, metadata={"hnsw:space": "cosine"})


def add_chunks(user_id: int, doc_id: int, chunks: list[str], embeddings: list[list[float]]):
    col = collection_for_user(user_id)
    ids = [f"{doc_id}-{i}" for i in range(len(chunks))]
    metadatas = [{"doc_id": doc_id, "ord": i} for i in range(len(chunks))]
    col.add(ids=ids, documents=chunks, embeddings=embeddings, metadatas=metadatas)


def query(user_id: int, query_embedding: list[float], k: int = 5, doc_ids: list[int] | None = None):
    col = collection_for_user(user_id)
    where = {"doc_id": {"$in": doc_ids}} if doc_ids else None
    res = col.query(query_embeddings=[query_embedding], n_results=k, where=where)
    out = []
    for i in range(len(res["ids"][0])):
        out.append({
            "id": res["ids"][0][i],
            "text": res["documents"][0][i],
            "distance": res["distances"][0][i],
            "metadata": res["metadatas"][0][i],
        })
    return out


def delete_doc(user_id: int, doc_id: int):
    col = collection_for_user(user_id)
    col.delete(where={"doc_id": doc_id})
