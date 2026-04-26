from fastapi import APIRouter, Depends
from app.deps import get_current_user
from app.models import User
from app.schemas.content import TutorIn
from app.services import llm

router = APIRouter()

STYLES = {
    "step_by_step": "You are a patient tutor. Use numbered steps and worked examples.",
    "socratic": "You are a Socratic tutor. Guide via questions; never give a direct answer first.",
    "exam_focused": "You are an exam coach. Cite syllabus points, marks distribution, and common traps.",
}


@router.post("/ask")
async def ask(payload: TutorIn, user: User = Depends(get_current_user)):
    sys = STYLES.get(payload.style, STYLES["step_by_step"])
    history_str = "\n".join(f"{m.get('role','')}: {m.get('content','')}" for m in payload.history[-8:])
    prompt = f"Conversation:\n{history_str}\n\nLatest question: {payload.question}"
    answer = await llm.chat(prompt, system=sys, language=user.language, temperature=0.4)
    return {"answer": answer, "style": payload.style}
