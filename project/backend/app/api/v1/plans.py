from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.deps import get_current_user
from app.models import StudyPlan, User
from app.schemas.content import PlanIn, PlanOut
from app.services import llm

router = APIRouter()


@router.post("", response_model=PlanOut)
async def create_plan(payload: PlanIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    prompt = (
        f"Build a personalized weekly study plan for grade {user.grade or 'unknown'} student.\n"
        f"Subjects: {', '.join(payload.subjects)}\nHours/week: {payload.hours_per_week}\n"
        f"Goals: {payload.goals}\nExam date: {payload.exam_date or 'N/A'}\n"
        f"Output Markdown: day-by-day with topics, time blocks, breaks, Saturday revision, Sunday mock test."
    )
    content = await llm.chat(prompt, language=user.language, temperature=0.5)
    sp = StudyPlan(user_id=user.id, title=f"Plan: {', '.join(payload.subjects)[:60]}", content=content)
    db.add(sp); await db.commit(); await db.refresh(sp)
    return sp


@router.get("", response_model=list[PlanOut])
async def list_plans(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(StudyPlan).where(StudyPlan.user_id == user.id).order_by(StudyPlan.created_at.desc()))
    return list(res.scalars())
