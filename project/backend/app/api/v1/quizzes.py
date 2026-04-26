import json
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.deps import get_current_user
from app.models import QuizResult, User
from app.schemas.content import QuizIn, QuizSubmitIn
from app.services import llm

router = APIRouter()


async def _difficulty(db: AsyncSession, user: User, topic: str) -> str:
    res = await db.execute(
        select(QuizResult).where(QuizResult.user_id == user.id, QuizResult.topic == topic)
        .order_by(QuizResult.created_at.desc()).limit(1)
    )
    p = res.scalar_one_or_none()
    if not p:
        return "medium"
    r = p.score / max(p.total, 1)
    return "hard" if r > 0.8 else ("easy" if r < 0.5 else "medium")


@router.post("/generate")
async def generate(payload: QuizIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    diff = await _difficulty(db, user, payload.topic)
    raw = await llm.chat(
        f"Generate a {diff} 5-question MCQ on '{payload.topic}' for a high schooler. "
        'Output ONLY JSON: {"questions":[{"q":"...","choices":["a","b","c","d"],"answer_index":0,"explanation":"..."}]}',
        system="You output only valid JSON. No prose.",
        temperature=0.3, language=user.language,
    )
    try:
        s = raw.find("{"); e = raw.rfind("}") + 1
        quiz = json.loads(raw[s:e])
    except Exception:
        quiz = {"questions": []}
    quiz["difficulty"] = diff
    return quiz


@router.post("/mock")
async def mock_test(payload: QuizIn, user: User = Depends(get_current_user)):
    raw = await llm.chat(
        f"Build a 20-question mock exam on '{payload.topic}' for grade {user.grade or '10'}. "
        'Mix MCQ + short answer. Output JSON: {"sections":[{"name":"...","items":[{"type":"mcq|short","q":"...","choices":[],"answer":"...","marks":1}]}],"total_marks":N,"duration_min":60}',
        system="Output strict JSON only.", language=user.language, temperature=0.4,
    )
    try:
        s = raw.find("{"); e = raw.rfind("}") + 1
        return json.loads(raw[s:e])
    except Exception:
        return {"sections": [], "total_marks": 0, "duration_min": 60}


@router.post("/submit")
async def submit(payload: QuizSubmitIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    db.add(QuizResult(user_id=user.id, topic=payload.topic, difficulty=payload.difficulty,
                      score=payload.score, total=payload.total))
    await db.commit()
    return {"ok": True}
