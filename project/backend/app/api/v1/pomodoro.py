from datetime import date
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.deps import get_current_user
from app.models import PomodoroSession, DailyTask, User
from app.schemas.content import PomodoroIn, TaskIn

router = APIRouter()


@router.post("/start")
async def start(payload: PomodoroIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    p = PomodoroSession(user_id=user.id, minutes=payload.minutes)
    db.add(p); await db.commit(); await db.refresh(p)
    return {"id": p.id, "minutes": p.minutes}


@router.post("/complete/{sid}")
async def complete(sid: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(PomodoroSession).where(PomodoroSession.id == sid, PomodoroSession.user_id == user.id))
    p = res.scalar_one_or_none()
    if p:
        p.completed = True; await db.commit()
    return {"ok": True}


@router.post("/tasks")
async def add_task(payload: TaskIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    t = DailyTask(user_id=user.id, text=payload.text, for_date=date.today())
    db.add(t); await db.commit(); await db.refresh(t)
    return {"id": t.id, "text": t.text, "done": t.done}


@router.post("/tasks/{tid}/toggle")
async def toggle(tid: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(DailyTask).where(DailyTask.id == tid, DailyTask.user_id == user.id))
    t = res.scalar_one_or_none()
    if t:
        t.done = not t.done; await db.commit()
    return {"ok": True}


@router.get("/tasks/today")
async def today(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    res = await db.execute(
        select(DailyTask).where(DailyTask.user_id == user.id, DailyTask.for_date == date.today())
        .order_by(DailyTask.id.asc())
    )
    return [{"id": t.id, "text": t.text, "done": t.done} for t in res.scalars()]
