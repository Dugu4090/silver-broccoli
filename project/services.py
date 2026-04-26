"""Business logic: plans, notes, quizzes, RAG, coding, exam strategy."""
import json
from datetime import date
from db import (
    SessionLocal, Note, QuizResult, StudyPlan, Flashcard,
    PomodoroSession, DailyTask, Room, RoomMessage, User,
)
from llm_client import llm
from search_client import web_search
import vector_store


# ---------- Plans ----------
def generate_plan(user, subjects, hours_per_week, goals, exam_date: str = ""):
    prompt = (
        f"Create a weekly study plan for grade {user.grade or 'unknown'} student.\n"
        f"Subjects: {', '.join(subjects)}\nHours/week: {hours_per_week}\nGoals: {goals}\n"
        f"Exam date (optional): {exam_date}\n"
        f"Return Markdown: day-by-day with topics, durations, breaks, a Saturday revision block, "
        f"and one Sunday mock-test block."
    )
    content = llm(prompt, language=user.language)
    db = SessionLocal()
    try:
        sp = StudyPlan(user_id=user.id, title=f"Plan: {', '.join(subjects)[:60]}", content=content)
        db.add(sp); db.commit()
    finally:
        db.close()
    return content


def list_plans(user):
    db = SessionLocal()
    try:
        return db.query(StudyPlan).filter(StudyPlan.user_id == user.id).order_by(StudyPlan.created_at.desc()).all()
    finally:
        db.close()


# ---------- Search + RAG ----------
def search_and_summarize(user, query: str):
    results = web_search(query, max_results=6)
    summary = llm(
        f"Summarize these results for a high schooler researching '{query}':\n{json.dumps(results)[:4500]}",
        system="You are a concise study assistant. Output Markdown bullets with [1][2] citations matching source order.",
        language=user.language,
    )
    return {"results": results, "summary": summary}


def rag_chat(user, question: str, doc_ids=None):
    hits = vector_store.search(user, question, k=5, doc_ids=doc_ids)
    if not hits:
        return {"answer": "No documents indexed yet. Upload a PDF/URL/YouTube first.", "citations": []}
    context = "\n\n".join(f"[{i+1}] {h['text']}" for i, h in enumerate(hits))
    answer = llm(
        f"Use ONLY the context below to answer. Cite sources as [1], [2].\n\nContext:\n{context}\n\nQuestion: {question}",
        system="You are a grounded tutor. If the context doesn't contain the answer, say so.",
        language=user.language,
    )
    return {"answer": answer, "citations": hits}


# ---------- Notes / summaries ----------
def create_note(user, topic, raw_content, summary_type="detailed"):
    style = {
        "short": "a 5-sentence concise summary",
        "detailed": "detailed study notes with headings, bullets, key terms in **bold**, and 5 review questions",
        "bullet": "a clean bullet-point outline only",
        "mindmap": "a Mermaid mindmap diagram inside ```mermaid``` fences, then a 3-bullet TL;DR",
    }.get(summary_type, "detailed study notes")
    notes_md = llm(
        f"Topic: {topic}\nSource:\n{raw_content[:8000]}\n\nProduce {style}.",
        system="You are an expert note-taker for high school students.",
        language=user.language,
    )
    db = SessionLocal()
    try:
        n = Note(user_id=user.id, topic=topic, content=notes_md, summary_type=summary_type)
        db.add(n); db.commit(); db.refresh(n)
        return n
    finally:
        db.close()


def list_notes(user):
    db = SessionLocal()
    try:
        return db.query(Note).filter(Note.user_id == user.id).order_by(Note.created_at.desc()).all()
    finally:
        db.close()


# ---------- Quizzes ----------
def adaptive_difficulty(user, topic):
    db = SessionLocal()
    try:
        prior = (
            db.query(QuizResult)
            .filter(QuizResult.user_id == user.id, QuizResult.topic == topic)
            .order_by(QuizResult.created_at.desc()).first()
        )
    finally:
        db.close()
    if not prior:
        return "medium"
    ratio = prior.score / max(prior.total, 1)
    return "hard" if ratio > 0.8 else ("easy" if ratio < 0.5 else "medium")


def generate_quiz(user, topic):
    difficulty = adaptive_difficulty(user, topic)
    raw = llm(
        f"Generate a {difficulty} 5-question MCQ on '{topic}' for a high schooler. "
        'Output ONLY JSON: {"questions":[{"q":"...","choices":["a","b","c","d"],"answer_index":0,"explanation":"..."}]}',
        system="You output only valid JSON. No prose, no fences.",
        temperature=0.3, language=user.language,
    )
    try:
        s = raw.find("{"); e = raw.rfind("}") + 1
        quiz = json.loads(raw[s:e])
    except Exception:
        quiz = {"questions": []}
    quiz["difficulty"] = difficulty
    return quiz


def record_quiz(user, topic, difficulty, score, total):
    db = SessionLocal()
    try:
        db.add(QuizResult(user_id=user.id, topic=topic, difficulty=difficulty, score=score, total=total))
        db.commit()
    finally:
        db.close()


# ---------- Coding assistant ----------
def code_help(user, language: str, code: str, question: str):
    return llm(
        f"Language: {language}\nCode:\n```{language}\n{code}\n```\nQuestion: {question}\n"
        f"If the code has bugs, identify them and provide a fixed version.",
        system="You are a senior coding mentor. Give step-by-step explanations, then the corrected code in a fenced block.",
        language=user.language, temperature=0.2,
    )


# ---------- Flashcards ----------
def generate_flashcards(user, topic: str, n: int = 10):
    raw = llm(
        f'Create {n} flashcards on "{topic}" for a high schooler. '
        'Output ONLY JSON: {"cards":[{"front":"...","back":"..."}]}',
        system="You output only valid JSON.", temperature=0.3, language=user.language,
    )
    try:
        s = raw.find("{"); e = raw.rfind("}") + 1
        data = json.loads(raw[s:e])
        cards = data.get("cards", [])
    except Exception:
        cards = []
    db = SessionLocal()
    try:
        for c in cards:
            db.add(Flashcard(user_id=user.id, deck=topic, front=c.get("front", ""), back=c.get("back", "")))
        db.commit()
    finally:
        db.close()
    return cards


# ---------- Pomodoro / tasks ----------
def start_pomodoro(user, minutes: int = 25):
    db = SessionLocal()
    try:
        p = PomodoroSession(user_id=user.id, minutes=minutes)
        db.add(p); db.commit(); db.refresh(p)
        return p
    finally:
        db.close()


def complete_pomodoro(session_id: int):
    db = SessionLocal()
    try:
        p = db.query(PomodoroSession).get(session_id)
        if p:
            p.completed = True; db.commit()
    finally:
        db.close()


def add_task(user, text: str):
    db = SessionLocal()
    try:
        t = DailyTask(user_id=user.id, text=text, for_date=date.today())
        db.add(t); db.commit()
    finally:
        db.close()


def toggle_task(task_id: int):
    db = SessionLocal()
    try:
        t = db.query(DailyTask).get(task_id)
        if t:
            t.done = not t.done; db.commit()
    finally:
        db.close()


def today_tasks(user):
    db = SessionLocal()
    try:
        return db.query(DailyTask).filter(
            DailyTask.user_id == user.id, DailyTask.for_date == date.today()
        ).order_by(DailyTask.id.asc()).all()
    finally:
        db.close()


# ---------- Exam strategy ----------
def exam_strategy(user, subjects: list[str], exam_date: str, weak_topics: list[str]):
    return llm(
        f"Build an exam strategy for grade {user.grade}. Subjects: {subjects}. "
        f"Exam: {exam_date}. Weak: {weak_topics}. "
        f"Provide: priority order, daily focus, last-3-days plan, exam-day checklist.",
        system="You are an exam coach. Be specific and actionable.", language=user.language,
    )


# ---------- Progress / weak areas ----------
def progress_summary(user):
    db = SessionLocal()
    try:
        results = db.query(QuizResult).filter(QuizResult.user_id == user.id).all()
        notes_count = db.query(Note).filter(Note.user_id == user.id).count()
        plans_count = db.query(StudyPlan).filter(StudyPlan.user_id == user.id).count()
        pomos = db.query(PomodoroSession).filter(
            PomodoroSession.user_id == user.id, PomodoroSession.completed == True  # noqa
        ).count()
    finally:
        db.close()
    by_topic = {}
    for r in results:
        by_topic.setdefault(r.topic, []).append(r.score / max(r.total, 1))
    averages = {t: sum(v) / len(v) for t, v in by_topic.items()}
    weak = sorted([t for t, a in averages.items() if a < 0.6])
    return {
        "quizzes_taken": len(results),
        "notes_count": notes_count,
        "plans_count": plans_count,
        "pomodoros": pomos,
        "streak": user.streak_count or 0,
        "avg_by_topic": averages,
        "weak_topics": weak,
    }


# ---------- Rooms ----------
def ensure_room(name: str, user):
    db = SessionLocal()
    try:
        r = db.query(Room).filter(Room.name == name).first()
        if not r:
            r = Room(name=name, created_by=user.id)
            db.add(r); db.commit(); db.refresh(r)
        return r
    finally:
        db.close()


def post_message(room_id: int, user: User, text: str):
    db = SessionLocal()
    try:
        m = RoomMessage(room_id=room_id, user_id=user.id, user_email=user.email, text=text)
        db.add(m); db.commit(); db.refresh(m)
        return m
    finally:
        db.close()


def list_messages(room_id: int, limit: int = 100):
    db = SessionLocal()
    try:
        return list(reversed(
            db.query(RoomMessage).filter(RoomMessage.room_id == room_id)
              .order_by(RoomMessage.id.desc()).limit(limit).all()
        ))
    finally:
        db.close()
