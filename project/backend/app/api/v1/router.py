from fastapi import APIRouter
from app.api.v1 import auth, users, plans, tutor, rag, notes, quizzes, flashcards, coding, pomodoro, rooms, analytics, admin

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(plans.router, prefix="/plans", tags=["plans"])
api_router.include_router(tutor.router, prefix="/tutor", tags=["tutor"])
api_router.include_router(rag.router, prefix="/rag", tags=["rag"])
api_router.include_router(notes.router, prefix="/notes", tags=["notes"])
api_router.include_router(quizzes.router, prefix="/quizzes", tags=["quizzes"])
api_router.include_router(flashcards.router, prefix="/flashcards", tags=["flashcards"])
api_router.include_router(coding.router, prefix="/coding", tags=["coding"])
api_router.include_router(pomodoro.router, prefix="/pomodoro", tags=["pomodoro"])
api_router.include_router(rooms.router, prefix="/rooms", tags=["rooms"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
