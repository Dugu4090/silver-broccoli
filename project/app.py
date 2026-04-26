"""StudyMate AI \u2014 single-file FastAPI app.
Serves the SPA at / and the JSON API under /api/*.
Works locally via `python app.py` and on Vercel via api/index.py.
"""
import os
import io
import re
import json
import math
import hashlib
from datetime import datetime, timedelta, date
from typing import Optional, List
from collections import Counter

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import (
    create_engine, Column, Integer, String, Text, DateTime, Date, Float,
    Boolean, ForeignKey,
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from passlib.context import CryptContext
from jose import jwt, JWTError
from dotenv import load_dotenv
import httpx

load_dotenv()

# ============================ Config ============================
IS_VERCEL = bool(os.getenv("VERCEL"))
DEFAULT_DB = "sqlite:////tmp/studymate.db" if IS_VERCEL else "sqlite:///./studymate.db"
DATABASE_URL = os.getenv("DATABASE_URL") or DEFAULT_DB
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
JWT_ALG = "HS256"
JWT_EXP_MIN = 60 * 24 * 7
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@studymate.local")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin1234")
DEFAULT_LANGUAGE = os.getenv("DEFAULT_LANGUAGE", "English")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ============================ Models ============================
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(20), default="student")
    full_name = Column(String(120), default="")
    grade = Column(String(10), default="")
    language = Column(String(40), default="English")
    streak_count = Column(Integer, default=0)
    last_active = Column(Date, default=date.today)
    created_at = Column(DateTime, default=datetime.utcnow)


class StudyPlan(Base):
    __tablename__ = "study_plans"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    title = Column(String(255))
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class Note(Base):
    __tablename__ = "notes"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    topic = Column(String(255))
    content = Column(Text)
    summary_type = Column(String(20), default="detailed")
    created_at = Column(DateTime, default=datetime.utcnow)


class QuizResult(Base):
    __tablename__ = "quiz_results"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    topic = Column(String(120))
    difficulty = Column(String(20))
    score = Column(Integer)
    total = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)


class Document(Base):
    __tablename__ = "documents"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    title = Column(String(255))
    source_type = Column(String(20))
    source_ref = Column(String(1024), default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class Chunk(Base):
    __tablename__ = "chunks"
    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("documents.id"), index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    text = Column(Text)
    ord = Column(Integer, default=0)


class Flashcard(Base):
    __tablename__ = "flashcards"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    deck = Column(String(120), default="general")
    front = Column(Text)
    back = Column(Text)
    ease = Column(Float, default=2.5)
    interval = Column(Integer, default=0)
    repetitions = Column(Integer, default=0)
    due_date = Column(Date, default=date.today)
    created_at = Column(DateTime, default=datetime.utcnow)


Base.metadata.create_all(bind=engine)


def ensure_admin():
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.email == ADMIN_EMAIL).first():
            db.add(User(email=ADMIN_EMAIL, hashed_password=pwd_ctx.hash(ADMIN_PASSWORD), role="admin"))
            db.commit()
    finally:
        db.close()


ensure_admin()

# ============================ Auth ============================
def hash_password(p: str) -> str: return pwd_ctx.hash(p)
def verify_password(p: str, h: str) -> bool: return pwd_ctx.verify(p, h)


def create_token(email: str) -> str:
    payload = {"sub": email, "exp": datetime.utcnow() + timedelta(minutes=JWT_EXP_MIN)}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _update_streak(user: User, db: Session):
    today = date.today()
    last = user.last_active or today
    if last == today:
        return
    user.streak_count = (user.streak_count or 0) + 1 if (today - last).days == 1 else 1
    user.last_active = today
    db.commit()


def get_current_user(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Missing bearer token")
    token = authorization.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except JWTError as e:
        raise HTTPException(401, f"Invalid token: {e}")
    u = db.query(User).filter(User.email == payload.get("sub")).first()
    if not u:
        raise HTTPException(401, "User not found")
    _update_streak(u, db)
    return u

# ============================ LLM (Groq) ============================
def llm(prompt: str, system: str = "You are a helpful tutor for high school students.",
        temperature: float = 0.4, language: str = None) -> str:
    language = language or DEFAULT_LANGUAGE
    sys_full = f"{system}\nAlways respond in {language}."
    if not GROQ_API_KEY:
        return "[LLM disabled \u2014 set GROQ_API_KEY in .env or Vercel env vars. Get a free key at https://console.groq.com]"
    try:
        r = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            json={
                "model": GROQ_MODEL,
                "messages": [
                    {"role": "system", "content": sys_full},
                    {"role": "user", "content": prompt},
                ],
                "temperature": temperature,
            },
            timeout=60,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"[LLM error: {e}]"

# ============================ Ingestion ============================
def extract_pdf(data: bytes) -> str:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    return "\n\n".join((p.extract_text() or "") for p in reader.pages)


def extract_url(url: str) -> str:
    from bs4 import BeautifulSoup
    r = httpx.get(url, timeout=30, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    for t in soup(["script", "style", "nav", "footer", "header"]):
        t.decompose()
    return re.sub(r"\n{3,}", "\n\n", soup.get_text("\n")).strip()


def extract_youtube(url_or_id: str) -> str:
    from youtube_transcript_api import YouTubeTranscriptApi
    m = re.search(r"(?:v=|youtu\.be/|/shorts/)([A-Za-z0-9_-]{11})", url_or_id)
    vid = m.group(1) if m else url_or_id
    tr = YouTubeTranscriptApi.get_transcript(vid)
    return " ".join(seg["text"] for seg in tr)


def chunk_text(text: str, size: int = 800, overlap: int = 100) -> List[str]:
    text = text.replace("\r", "")
    out, i = [], 0
    while i < len(text):
        out.append(text[i:i + size])
        i += size - overlap
    return [c for c in out if c.strip()]

# ============================ RAG (keyword/TF-IDF, no embedding service) ============================
_WORD_RE = re.compile(r"[A-Za-z0-9_]+")


def _tokens(s: str) -> List[str]:
    return [w.lower() for w in _WORD_RE.findall(s) if len(w) > 1]


def rag_search(db: Session, user_id: int, query: str, k: int = 5,
               doc_ids: Optional[List[int]] = None) -> List[dict]:
    q = db.query(Chunk).filter(Chunk.user_id == user_id)
    if doc_ids:
        q = q.filter(Chunk.document_id.in_(doc_ids))
    chunks = q.all()
    if not chunks:
        return []
    qtoks = set(_tokens(query))
    if not qtoks:
        return []
    # Simple TF-IDF-ish scoring
    df = Counter()
    docs_tokens = []
    for c in chunks:
        toks = _tokens(c.text)
        docs_tokens.append(toks)
        for t in set(toks):
            df[t] += 1
    N = len(chunks)
    scored = []
    for c, toks in zip(chunks, docs_tokens):
        tf = Counter(toks)
        score = 0.0
        for t in qtoks:
            if t in tf:
                idf = math.log((N + 1) / (df[t] + 1)) + 1
                score += tf[t] * idf
        if score > 0:
            scored.append((score, c))
    scored.sort(key=lambda x: x[0], reverse=True)
    max_s = scored[0][0] if scored else 1.0
    return [
        {"score": round(s / max_s, 3), "text": c.text, "document_id": c.document_id, "chunk_id": c.id}
        for s, c in scored[:k]
    ]

# ============================ SM-2 ============================
def apply_sm2(card: Flashcard, quality: int):
    if quality < 3:
        card.repetitions = 0; card.interval = 1
    else:
        if card.repetitions == 0: card.interval = 1
        elif card.repetitions == 1: card.interval = 6
        else: card.interval = int(round((card.interval or 1) * (card.ease or 2.5)))
        card.repetitions = (card.repetitions or 0) + 1
    card.ease = max(1.3, (card.ease or 2.5) + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)))
    card.due_date = date.today() + timedelta(days=card.interval)
    return card

# ============================ Schemas ============================
class SignupIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    full_name: str = ""
    grade: str = ""
    language: str = "English"

class LoginIn(BaseModel):
    email: EmailStr
    password: str

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"

class PlanIn(BaseModel):
    subjects: List[str]
    hours_per_week: int = 14
    goals: str = ""
    exam_date: str = ""

class NoteIn(BaseModel):
    topic: str
    raw_content: str
    summary_type: str = "detailed"

class TutorIn(BaseModel):
    question: str
    history: List[dict] = []
    style: str = "step_by_step"

class RagAskIn(BaseModel):
    question: str
    document_ids: Optional[List[int]] = None

class IngestUrlIn(BaseModel):
    url: str
    title: Optional[str] = None

class QuizGenIn(BaseModel):
    topic: str

class QuizSubmitIn(BaseModel):
    topic: str
    difficulty: str
    score: int
    total: int

class FlashGenIn(BaseModel):
    topic: str
    n: int = 10

class FlashReviewIn(BaseModel):
    card_id: int
    quality: int = Field(ge=0, le=5)

class CodeHelpIn(BaseModel):
    language: str
    code: str
    question: str = ""

class SearchIn(BaseModel):
    query: str

class ExamStrategyIn(BaseModel):
    subjects: List[str]
    exam_date: str
    weak_topics: List[str] = []

# ============================ App ============================
app = FastAPI(title="StudyMate AI")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat(), "llm": bool(GROQ_API_KEY)}

# ---------- Auth ----------
@app.post("/api/auth/signup", response_model=TokenOut)
def signup(payload: SignupIn, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(400, "Email already registered")
    u = User(
        email=payload.email, hashed_password=hash_password(payload.password),
        full_name=payload.full_name, grade=payload.grade,
        language=payload.language, role="student",
    )
    db.add(u); db.commit(); db.refresh(u)
    return TokenOut(access_token=create_token(u.email))


@app.post("/api/auth/login", response_model=TokenOut)
def login(payload: LoginIn, db: Session = Depends(get_db)):
    u = db.query(User).filter(User.email == payload.email).first()
    if not u or not verify_password(payload.password, u.hashed_password):
        raise HTTPException(401, "Bad email or password")
    return TokenOut(access_token=create_token(u.email))


@app.get("/api/me")
def me(user: User = Depends(get_current_user)):
    return {
        "id": user.id, "email": user.email, "role": user.role,
        "full_name": user.full_name, "grade": user.grade,
        "language": user.language, "streak_count": user.streak_count or 0,
    }

# ---------- Plans ----------
@app.post("/api/plans")
def create_plan(payload: PlanIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    prompt = (
        f"Build a personalized weekly study plan for grade {user.grade or 'unknown'}.\n"
        f"Subjects: {', '.join(payload.subjects)}\nHours/week: {payload.hours_per_week}\n"
        f"Goals: {payload.goals}\nExam date: {payload.exam_date or 'N/A'}\n"
        f"Output Markdown with day-by-day schedule, time blocks, breaks, Sat revision, Sun mock test."
    )
    content = llm(prompt, language=user.language, temperature=0.5)
    sp = StudyPlan(user_id=user.id, title=f"Plan: {', '.join(payload.subjects)[:60]}", content=content)
    db.add(sp); db.commit(); db.refresh(sp)
    return {"id": sp.id, "title": sp.title, "content": sp.content,
            "created_at": sp.created_at.isoformat()}


@app.get("/api/plans")
def list_plans(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(StudyPlan).filter(StudyPlan.user_id == user.id).order_by(StudyPlan.created_at.desc()).all()
    return [{"id": p.id, "title": p.title, "content": p.content,
             "created_at": p.created_at.isoformat()} for p in rows]

# ---------- Tutor ----------
TUTOR_STYLES = {
    "step_by_step": "You are a patient tutor. Use numbered steps and worked examples.",
    "socratic": "You are a Socratic tutor. Guide via questions; never give a direct answer first.",
    "exam_focused": "You are an exam coach. Highlight syllabus points, marks distribution, common traps.",
}


@app.post("/api/tutor")
def tutor_ask(payload: TutorIn, user: User = Depends(get_current_user)):
    sys = TUTOR_STYLES.get(payload.style, TUTOR_STYLES["step_by_step"])
    history_str = "\n".join(f"{m.get('role','')}: {m.get('content','')}" for m in payload.history[-8:])
    answer = llm(
        f"Conversation:\n{history_str}\n\nLatest question: {payload.question}",
        system=sys, language=user.language, temperature=0.4,
    )
    return {"answer": answer, "style": payload.style}

# ---------- Notes ----------
NOTE_STYLES = {
    "short": "a 5-sentence concise summary",
    "detailed": "detailed study notes with headings, bullets, key terms in **bold**, and 5 review questions",
    "bullet": "a clean bullet-point outline only",
    "mindmap": "a Mermaid mindmap diagram inside ```mermaid``` fences, then a 3-bullet TL;DR",
}


@app.post("/api/notes")
def create_note(payload: NoteIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    style = NOTE_STYLES.get(payload.summary_type, NOTE_STYLES["detailed"])
    content = llm(
        f"Topic: {payload.topic}\nSource:\n{payload.raw_content[:8000]}\n\nProduce {style}.",
        system="You are an expert note-taker for high school students.",
        language=user.language, temperature=0.3,
    )
    n = Note(user_id=user.id, topic=payload.topic, content=content, summary_type=payload.summary_type)
    db.add(n); db.commit(); db.refresh(n)
    return {"id": n.id, "topic": n.topic, "content": n.content,
            "summary_type": n.summary_type, "created_at": n.created_at.isoformat()}


@app.get("/api/notes")
def list_notes(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(Note).filter(Note.user_id == user.id).order_by(Note.created_at.desc()).all()
    return [{"id": n.id, "topic": n.topic, "content": n.content,
             "summary_type": n.summary_type, "created_at": n.created_at.isoformat()} for n in rows]

# ---------- RAG ----------
@app.post("/api/rag/ingest/url")
def ingest_url_endpoint(payload: IngestUrlIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    is_yt = ("youtube.com" in payload.url) or ("youtu.be" in payload.url)
    try:
        text = extract_youtube(payload.url) if is_yt else extract_url(payload.url)
    except Exception as e:
        raise HTTPException(400, f"Failed to fetch: {e}")
    src = "youtube" if is_yt else "url"
    doc = Document(user_id=user.id, title=payload.title or payload.url[:80],
                   source_type=src, source_ref=payload.url)
    db.add(doc); db.commit(); db.refresh(doc)
    for i, c in enumerate(chunk_text(text)):
        db.add(Chunk(document_id=doc.id, user_id=user.id, text=c, ord=i))
    db.commit()
    return {"document_id": doc.id, "chunks": len(chunk_text(text)), "title": doc.title}


@app.post("/api/rag/ingest/pdf")
async def ingest_pdf_endpoint(file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "PDF required")
    data = await file.read()
    try:
        text = extract_pdf(data)
    except Exception as e:
        raise HTTPException(400, f"Bad PDF: {e}")
    doc = Document(user_id=user.id, title=file.filename, source_type="pdf", source_ref=file.filename)
    db.add(doc); db.commit(); db.refresh(doc)
    chunks = chunk_text(text)
    for i, c in enumerate(chunks):
        db.add(Chunk(document_id=doc.id, user_id=user.id, text=c, ord=i))
    db.commit()
    return {"document_id": doc.id, "chunks": len(chunks), "title": doc.title}


@app.get("/api/rag/documents")
def list_docs(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(Document).filter(Document.user_id == user.id).order_by(Document.created_at.desc()).all()
    return [{"id": d.id, "title": d.title, "source_type": d.source_type,
             "created_at": d.created_at.isoformat()} for d in rows]


@app.delete("/api/rag/documents/{doc_id}")
def delete_doc(doc_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.query(Chunk).filter(Chunk.document_id == doc_id, Chunk.user_id == user.id).delete()
    db.query(Document).filter(Document.id == doc_id, Document.user_id == user.id).delete()
    db.commit()
    return {"ok": True}


@app.post("/api/rag/ask")
def rag_ask(payload: RagAskIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    hits = rag_search(db, user.id, payload.question, k=5, doc_ids=payload.document_ids)
    if not hits:
        return {"answer": "No documents indexed yet. Upload a PDF/URL/YouTube first.",
                "citations": [], "confidence": 0.0}
    context = "\n\n".join(f"[{i+1}] {h['text']}" for i, h in enumerate(hits))
    answer = llm(
        f"Use ONLY the context to answer. Cite as [1], [2]. If not answerable, say so.\n\n"
        f"Context:\n{context}\n\nQuestion: {payload.question}",
        system="You are a grounded study tutor. Cite sources. Be precise.",
        language=user.language, temperature=0.2,
    )
    confidence = round(sum(h["score"] for h in hits) / len(hits), 3)
    return {
        "answer": answer, "confidence": confidence,
        "citations": [
            {"index": i + 1, "text": h["text"][:600], "doc_id": h["document_id"], "score": h["score"]}
            for i, h in enumerate(hits)
        ],
    }

# ---------- Search ----------
@app.post("/api/search")
def web_search(payload: SearchIn, user: User = Depends(get_current_user)):
    from duckduckgo_search import DDGS
    try:
        with DDGS() as d:
            results = list(d.text(payload.query, max_results=6))
    except Exception as e:
        raise HTTPException(500, f"Search error: {e}")
    results = [{"title": r.get("title", ""), "url": r.get("href", ""), "snippet": r.get("body", "")} for r in results]
    summary = llm(
        f"Summarize for a high schooler researching '{payload.query}':\n{json.dumps(results)[:4500]}",
        system="Concise study assistant. Markdown bullets with [1][2] citations matching source order.",
        language=user.language, temperature=0.3,
    )
    return {"results": results, "summary": summary}

# ---------- Quizzes ----------
@app.post("/api/quiz/generate")
def quiz_generate(payload: QuizGenIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    prior = (db.query(QuizResult)
             .filter(QuizResult.user_id == user.id, QuizResult.topic == payload.topic)
             .order_by(QuizResult.created_at.desc()).first())
    if not prior:
        diff = "medium"
    else:
        ratio = prior.score / max(prior.total, 1)
        diff = "hard" if ratio > 0.8 else ("easy" if ratio < 0.5 else "medium")
    raw = llm(
        f"Generate a {diff} 5-question MCQ on '{payload.topic}' for a high schooler. "
        'Output ONLY JSON: {"questions":[{"q":"...","choices":["a","b","c","d"],"answer_index":0,"explanation":"..."}]}',
        system="You output only valid JSON. No prose.", temperature=0.3, language=user.language,
    )
    try:
        s = raw.find("{"); e = raw.rfind("}") + 1
        quiz = json.loads(raw[s:e])
    except Exception:
        quiz = {"questions": []}
    quiz["difficulty"] = diff
    return quiz


@app.post("/api/quiz/submit")
def quiz_submit(payload: QuizSubmitIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.add(QuizResult(user_id=user.id, topic=payload.topic, difficulty=payload.difficulty,
                      score=payload.score, total=payload.total))
    db.commit()
    return {"ok": True}

# ---------- Flashcards ----------
@app.post("/api/flashcards/generate")
def flash_gen(payload: FlashGenIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    raw = llm(
        f'Create {payload.n} flashcards on "{payload.topic}" for grade {user.grade or "10"}. '
        'Output ONLY JSON: {"cards":[{"front":"...","back":"..."}]}',
        system="Output strict JSON only.", temperature=0.3, language=user.language,
    )
    cards = []
    try:
        s = raw.find("{"); e = raw.rfind("}") + 1
        cards = json.loads(raw[s:e]).get("cards", [])
    except Exception:
        pass
    for c in cards:
        db.add(Flashcard(user_id=user.id, deck=payload.topic,
                         front=c.get("front", ""), back=c.get("back", "")))
    db.commit()
    return {"created": len(cards)}


@app.get("/api/flashcards/due")
def flash_due(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (db.query(Flashcard)
            .filter(Flashcard.user_id == user.id, Flashcard.due_date <= date.today())
            .order_by(Flashcard.due_date.asc()).all())
    return [{"id": c.id, "deck": c.deck, "front": c.front, "back": c.back,
             "due_date": c.due_date.isoformat()} for c in rows]


@app.post("/api/flashcards/review")
def flash_review(payload: FlashReviewIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = db.query(Flashcard).filter(Flashcard.id == payload.card_id, Flashcard.user_id == user.id).first()
    if not c:
        raise HTTPException(404, "Card not found")
    apply_sm2(c, payload.quality)
    db.commit()
    return {"ok": True, "next_due": c.due_date.isoformat()}

# ---------- Coding ----------
@app.post("/api/coding/help")
def coding_help(payload: CodeHelpIn, user: User = Depends(get_current_user)):
    answer = llm(
        f"Language: {payload.language}\nCode:\n```{payload.language}\n{payload.code}\n```\n"
        f"Question: {payload.question or 'Explain and improve this code.'}\n"
        f"If buggy, identify, fix, and explain why step-by-step.",
        system="You are a senior coding mentor. Give clear steps then a fenced corrected block.",
        language=user.language, temperature=0.2,
    )
    return {"answer": answer}

# ---------- Exam strategy ----------
@app.post("/api/exam/strategy")
def exam_strategy(payload: ExamStrategyIn, user: User = Depends(get_current_user)):
    answer = llm(
        f"Build an exam strategy for grade {user.grade}. Subjects: {payload.subjects}. "
        f"Exam date: {payload.exam_date}. Weak areas: {payload.weak_topics}. "
        f"Provide priority order, daily focus, last-3-days plan, exam-day checklist.",
        system="You are an exam coach. Be specific and actionable.", language=user.language,
    )
    return {"answer": answer}

# ---------- Analytics ----------
@app.get("/api/analytics/progress")
def progress(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    results = db.query(QuizResult).filter(QuizResult.user_id == user.id).all()
    notes_count = db.query(Note).filter(Note.user_id == user.id).count()
    plans_count = db.query(StudyPlan).filter(StudyPlan.user_id == user.id).count()
    docs_count = db.query(Document).filter(Document.user_id == user.id).count()
    by_topic = {}
    for r in results:
        by_topic.setdefault(r.topic, []).append(r.score / max(r.total, 1))
    averages = {t: sum(v) / len(v) for t, v in by_topic.items()}
    weak = sorted([t for t, a in averages.items() if a < 0.6])
    return {
        "streak": user.streak_count or 0,
        "quizzes_taken": len(results),
        "notes_count": notes_count,
        "plans_count": plans_count,
        "docs_count": docs_count,
        "avg_by_topic": averages,
        "weak_topics": weak,
    }

# ============================ Static frontend ============================
_STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
if os.path.isdir(_STATIC_DIR):
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

    @app.get("/")
    def index():
        return FileResponse(os.path.join(_STATIC_DIR, "index.html"))

    @app.get("/{path:path}")
    def spa(path: str):
        # Fall back to index.html for SPA routes that aren't API
        if path.startswith("api/"):
            raise HTTPException(404, "Not found")
        full = os.path.join(_STATIC_DIR, path)
        if os.path.isfile(full):
            return FileResponse(full)
        return FileResponse(os.path.join(_STATIC_DIR, "index.html"))

# ============================ Run ============================
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    print(f"\n\ud83c\udf93 StudyMate AI running on http://localhost:{port}")
    if not GROQ_API_KEY:
        print("\u26a0\ufe0f  GROQ_API_KEY not set \u2014 LLM features will be disabled.")
        print("   Get a free key at https://console.groq.com and add it to .env\n")
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=True)
