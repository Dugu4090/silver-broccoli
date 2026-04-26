from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.deps import get_current_user
from app.models import User, Document
from app.schemas.content import RagIn, IngestUrlIn
from app.services import ingestion, llm, vectorstore, rag, search
from app.workers.tasks import ingest_pdf_task, ingest_url_task, ingest_youtube_task

router = APIRouter()


@router.post("/ingest/url")
async def ingest_url(payload: IngestUrlIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    is_yt = ("youtube.com" in payload.url) or ("youtu.be" in payload.url)
    src = "youtube" if is_yt else "url"
    doc = Document(user_id=user.id, title=payload.title or payload.url[:80],
                   source_type=src, source_ref=payload.url, chroma_collection=f"user_{user.id}")
    db.add(doc); await db.commit(); await db.refresh(doc)
    if is_yt:
        ingest_youtube_task.delay(user.id, doc.id, payload.url)
    else:
        ingest_url_task.delay(user.id, doc.id, payload.url)
    return {"document_id": doc.id, "status": "queued"}


@router.post("/ingest/pdf")
async def ingest_pdf(file: UploadFile = File(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "PDF required")
    data = await file.read()
    doc = Document(user_id=user.id, title=file.filename, source_type="pdf",
                   source_ref=file.filename, chroma_collection=f"user_{user.id}")
    db.add(doc); await db.commit(); await db.refresh(doc)
    ingest_pdf_task.delay(user.id, doc.id, data)
    return {"document_id": doc.id, "status": "queued"}


@router.get("/documents")
async def documents(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Document).where(Document.user_id == user.id).order_by(Document.created_at.desc()))
    rows = list(res.scalars())
    return [{"id": d.id, "title": d.title, "source_type": d.source_type, "status": d.status,
             "created_at": d.created_at.isoformat()} for d in rows]


@router.delete("/documents/{doc_id}")
async def delete_doc(doc_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await db.execute(delete(Document).where(Document.id == doc_id, Document.user_id == user.id))
    await db.commit()
    vectorstore.delete_doc(user.id, doc_id)
    return {"ok": True}


@router.post("/ask")
async def ask(payload: RagIn, user: User = Depends(get_current_user)):
    return await rag.answer(user.id, user.language, payload.question, payload.document_ids)


@router.get("/search")
async def web(query: str, user: User = Depends(get_current_user)):
    results = search.web_search(query, max_results=6)
    summary = await rag.summarize_search(user.language, query, results)
    return {"results": results, "summary": summary}
