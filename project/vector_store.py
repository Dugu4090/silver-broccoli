"""SQLite-backed vector store using numpy cosine similarity."""
import numpy as np
from db import SessionLocal, Chunk, Document
from llm_client import embed
from logging_config import log


def _chunk_text(text: str, size: int = 800, overlap: int = 100):
    text = text.replace("\r", "")
    out = []
    i = 0
    while i < len(text):
        out.append(text[i : i + size])
        i += size - overlap
    return [c for c in out if c.strip()]


def ingest(user, title: str, source_type: str, source_ref: str, full_text: str) -> Document:
    db = SessionLocal()
    try:
        doc = Document(user_id=user.id, title=title, source_type=source_type, source_ref=source_ref or "")
        db.add(doc); db.commit(); db.refresh(doc)
        for i, c in enumerate(_chunk_text(full_text)):
            v = embed(c)
            db.add(Chunk(document_id=doc.id, user_id=user.id, text=c, embedding=v.tobytes(), ord=i))
        db.commit()
        log.info(f"Ingested doc {doc.id} ({title}) for user {user.id}")
        return doc
    finally:
        db.close()


def _cos(a: np.ndarray, b: np.ndarray) -> float:
    na = np.linalg.norm(a); nb = np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def search(user, query: str, k: int = 5, doc_ids: list[int] | None = None):
    qv = embed(query)
    db = SessionLocal()
    try:
        q = db.query(Chunk).filter(Chunk.user_id == user.id)
        if doc_ids:
            q = q.filter(Chunk.document_id.in_(doc_ids))
        chunks = q.all()
        scored = []
        for c in chunks:
            v = np.frombuffer(c.embedding, dtype=np.float32)
            scored.append((_cos(qv, v), c))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {"score": s, "text": c.text, "document_id": c.document_id, "chunk_id": c.id}
            for s, c in scored[:k]
        ]
    finally:
        db.close()


def list_documents(user):
    db = SessionLocal()
    try:
        return db.query(Document).filter(Document.user_id == user.id).order_by(Document.created_at.desc()).all()
    finally:
        db.close()


def delete_document(user, doc_id: int):
    db = SessionLocal()
    try:
        db.query(Chunk).filter(Chunk.document_id == doc_id, Chunk.user_id == user.id).delete()
        db.query(Document).filter(Document.id == doc_id, Document.user_id == user.id).delete()
        db.commit()
    finally:
        db.close()
