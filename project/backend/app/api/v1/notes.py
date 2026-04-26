from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.deps import get_current_user
from app.models import Note, User
from app.schemas.content import NoteIn, NoteOut
from app.services import llm

router = APIRouter()

STYLES = {
    "short": "a 5-sentence concise summary",
    "detailed": "detailed study notes with headings, bullets, key terms in **bold**, and 5 review questions",
    "bullet": "a clean bullet-point outline only",
    "mindmap": "a Mermaid mindmap diagram inside ```mermaid``` fences, then a 3-bullet TL;DR",
}


@router.post("", response_model=NoteOut)
async def create(payload: NoteIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    style = STYLES.get(payload.summary_type, STYLES["detailed"])
    content = await llm.chat(
        f"Topic: {payload.topic}\nSource:\n{payload.raw_content[:8000]}\n\nProduce {style}.",
        system="You are an expert note-taker for high school students.",
        language=user.language, temperature=0.3,
    )
    n = Note(user_id=user.id, topic=payload.topic, content=content, summary_type=payload.summary_type)
    db.add(n); await db.commit(); await db.refresh(n)
    return n


@router.get("", response_model=list[NoteOut])
async def list_notes(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Note).where(Note.user_id == user.id).order_by(Note.created_at.desc()))
    return list(res.scalars())
