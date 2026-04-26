from typing import List, Optional
from datetime import datetime, date
from pydantic import BaseModel, Field


class PlanIn(BaseModel):
    subjects: List[str] = Field(min_length=1)
    hours_per_week: int = Field(ge=1, le=80)
    goals: str = ""
    exam_date: Optional[str] = ""


class PlanOut(BaseModel):
    id: int
    title: str
    content: str
    created_at: datetime

    class Config:
        from_attributes = True


class NoteIn(BaseModel):
    topic: str
    raw_content: str
    summary_type: str = "detailed"


class NoteOut(BaseModel):
    id: int
    topic: str
    content: str
    summary_type: str
    created_at: datetime

    class Config:
        from_attributes = True


class QuizIn(BaseModel):
    topic: str


class QuizSubmitIn(BaseModel):
    topic: str
    difficulty: str
    score: int
    total: int


class FlashcardGenIn(BaseModel):
    topic: str
    n: int = 10


class FlashcardReviewIn(BaseModel):
    card_id: int
    quality: int = Field(ge=0, le=5)


class TutorIn(BaseModel):
    question: str
    history: list[dict] = []
    style: str = "step_by_step"  # step_by_step | socratic | exam_focused


class RagIn(BaseModel):
    question: str
    document_ids: Optional[List[int]] = None


class IngestUrlIn(BaseModel):
    url: str
    title: Optional[str] = None


class CodeHelpIn(BaseModel):
    language: str
    code: str
    question: str = ""
    run: bool = False


class ExamStrategyIn(BaseModel):
    subjects: List[str]
    exam_date: str
    weak_topics: List[str] = []


class TaskIn(BaseModel):
    text: str


class PomodoroIn(BaseModel):
    minutes: int = 25
