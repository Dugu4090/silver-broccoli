import json
from datetime import date
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.deps import get_current_user
from app.models import Flashcard, User
from app.schemas.content import FlashcardGenIn, FlashcardReviewIn
from app.services import llm, sm2

router = APIRouter()


@router.post("/generate")
async def generate(payload: FlashcardGenIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    raw = await llm.chat(
        f'Create {payload.n} flashcards on "{payload.topic}" for grade {user.grade or "10"}. '
        'Output ONLY JSON: {"cards":[{"front":"...","back":"..."}]}',
        system="Output strict JSON only.", language=user.language, temperature=0.3,
    )
    try:
        s = raw.find("{"); e = raw.rfind("}") + 1
        data = json.loads(raw[s:e])
        cards = data.get("cards", [])
    except Exception:
        cards = []
    for c in cards:
        db.add(Flashcard(user_id=user.id, deck=payload.topic,
                         front=c.get("front", ""), back=c.get("back", "")))
    await db.commit()
    return {"created": len(cards)}


@router.get("/due")
async def due(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    res = await db.execute(
        select(Flashcard).where(Flashcard.user_id == user.id, Flashcard.due_date <= date.today())
        .order_by(Flashcard.due_date.asc())
    )
    rows = list(res.scalars())
    return [{"id": c.id, "deck": c.deck, "front": c.front, "back": c.back,
             "due_date": c.due_date.isoformat()} for c in rows]


@router.post("/review")
async def review(payload: FlashcardReviewIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Flashcard).where(Flashcard.id == payload.card_id, Flashcard.user_id == user.id))
    c = res.scalar_one_or_none()
    if not c:
        return {"ok": False}
    sm2.apply_sm2(c, payload.quality)
    await db.commit()
    return {"ok": True, "next_due": c.due_date.isoformat()}
