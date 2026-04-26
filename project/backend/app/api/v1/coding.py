from fastapi import APIRouter, Depends
from app.deps import get_current_user
from app.models import User
from app.schemas.content import CodeHelpIn
from app.services import llm, code_exec

router = APIRouter()


@router.post("/help")
async def help_(payload: CodeHelpIn, user: User = Depends(get_current_user)):
    answer = await llm.chat(
        f"Language: {payload.language}\nCode:\n```{payload.language}\n{payload.code}\n```\n"
        f"Question: {payload.question or 'Explain and improve this code.'}\n"
        f"If buggy, identify, fix, and explain why step-by-step.",
        system="You are a senior coding mentor. Give clear steps then a fenced corrected block.",
        language=user.language, temperature=0.2,
    )
    result = {"answer": answer}
    if payload.run and payload.language.lower() == "python":
        result["execution"] = code_exec.run_python(payload.code, timeout=5)
    return result
