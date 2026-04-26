import os
import json
from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, Session, relationship
from passlib.context import CryptContext
from jose import jwt, JWTError
from dotenv import load_dotenv
import httpx
from openai import OpenAI

load_dotenv()

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret")
JWT_ALG = "HS256"
JWT_EXP_MIN = 60 * 24
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./studymate.db")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# ---------- Models ----------
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    grade = Column(String, default="")
    notes = relationship("Note", back_populates="owner")
    quiz_results = relationship("QuizResult", back_populates="owner")

class Note(Base):
    __tablename__ = "notes"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    topic = Column(String)
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    owner = relationship("User", back_populates="notes")

class QuizResult(Base):
    __tablename__ = "quiz_results"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    topic = Column(String)
    difficulty = Column(String)
    score = Column(Integer)
    total = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    owner = relationship("User", back_populates="quiz_results")

Base.metadata.create_all(bind=engine)

# ---------- Schemas ----------
class UserCreate(BaseModel):
    email: str
    password: str
    grade: Optional[str] = ""

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class PlanReq(BaseModel):
    subjects: List[str]
    hours_per_week: int
    goals: str = ""

class SearchReq(BaseModel):
    query: str

class NoteReq(BaseModel):
    topic: str
    raw_content: str

class QuizReq(BaseModel):
    topic: str

class QuizSubmit(BaseModel):
    topic: str
    difficulty: str
    score: int
    total: int

# ---------- Auth helpers ----------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def create_token(sub: str) -> str:
    payload = {"sub": sub, "exp": datetime.utcnow() + timedelta(minutes=JWT_EXP_MIN)}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    cred_exc = HTTPException(status_code=401, detail="Invalid credentials")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        email = payload.get("sub")
        if not email:
            raise cred_exc
    except JWTError:
        raise cred_exc
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise cred_exc
    return user

# ---------- App ----------
app = FastAPI(title="StudyMate AI")

@app.post("/auth/signup", response_model=Token)
def signup(payload: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(400, "Email already registered")
    user = User(email=payload.email, hashed_password=pwd_ctx.hash(payload.password), grade=payload.grade or "")
    db.add(user); db.commit(); db.refresh(user)
    return Token(access_token=create_token(user.email))

@app.post("/auth/login", response_model=Token)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form.username).first()
    if not user or not pwd_ctx.verify(form.password, user.hashed_password):
        raise HTTPException(401, "Bad email or password")
    return Token(access_token=create_token(user.email))

@app.get("/me")
def me(user: User = Depends(get_current_user)):
    return {"email": user.email, "grade": user.grade}

# ---------- AI helpers ----------
def llm(prompt: str, system: str = "You are a helpful tutor for high school students.") -> str:
    if not client:
        return "[LLM disabled \u2014 set OPENAI_API_KEY]"
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        temperature=0.6,
    )
    return resp.choices[0].message.content

# ---------- Features ----------
@app.post("/plan")
def study_plan(req: PlanReq, user: User = Depends(get_current_user)):
    prompt = (
        f"Create a weekly study plan for a high school student (grade: {user.grade or 'unknown'}).\n"
        f"Subjects: {', '.join(req.subjects)}\nHours per week: {req.hours_per_week}\nGoals: {req.goals}\n"
        f"Return a clear day-by-day Markdown schedule with specific topics and short breaks."
    )
    return {"plan": llm(prompt)}

@app.post("/search")
def web_search(req: SearchReq, user: User = Depends(get_current_user)):
    if not TAVILY_API_KEY:
        raise HTTPException(500, "TAVILY_API_KEY not set")
    r = httpx.post(
        "https://api.tavily.com/search",
        json={"api_key": TAVILY_API_KEY, "query": req.query, "max_results": 5, "include_answer": True},
        timeout=20,
    )
    r.raise_for_status()
    data = r.json()
    summary = llm(
        f"Summarize these results for a high schooler studying '{req.query}':\n{json.dumps(data.get('results', []))[:4000]}",
        system="You are a concise study assistant. Output Markdown bullet points.",
    )
    return {"answer": data.get("answer"), "results": data.get("results", []), "summary": summary}

@app.post("/notes")
def create_notes(req: NoteReq, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    notes_md = llm(
        f"Topic: {req.topic}\nSource:\n{req.raw_content[:6000]}\n\nCreate clean study notes with headings, bullet points, and 5 review questions at the end.",
        system="You are an expert note-taker for high school students.",
    )
    note = Note(user_id=user.id, topic=req.topic, content=notes_md)
    db.add(note); db.commit(); db.refresh(note)
    return {"id": note.id, "topic": note.topic, "content": note.content}

@app.get("/notes")
def list_notes(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.query(Note).filter(Note.user_id == user.id).order_by(Note.created_at.desc()).all()
    return [{"id": n.id, "topic": n.topic, "content": n.content, "created_at": n.created_at.isoformat()} for n in rows]

@app.post("/quiz")
def adaptive_quiz(req: QuizReq, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    prior = (
        db.query(QuizResult)
        .filter(QuizResult.user_id == user.id, QuizResult.topic == req.topic)
        .order_by(QuizResult.created_at.desc())
        .first()
    )
    if not prior:
        difficulty = "medium"
    else:
        ratio = prior.score / max(prior.total, 1)
        difficulty = "hard" if ratio > 0.8 else ("easy" if ratio < 0.5 else "medium")

    prompt = (
        f"Generate a {difficulty} 5-question multiple-choice quiz on '{req.topic}' for a high school student. "
        f"Return strict JSON: {{\"questions\":[{{\"q\":..., \"choices\":[...], \"answer_index\":0}}]}}"
    )
    raw = llm(prompt, system="You output only valid JSON. No prose.")
    try:
        start = raw.find("{"); end = raw.rfind("}") + 1
        quiz = json.loads(raw[start:end])
    except Exception:
        quiz = {"questions": []}
    return {"difficulty": difficulty, **quiz}

@app.post("/quiz/submit")
def quiz_submit(req: QuizSubmit, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    qr = QuizResult(user_id=user.id, topic=req.topic, difficulty=req.difficulty, score=req.score, total=req.total)
    db.add(qr); db.commit()
    return {"ok": True}

# ---------- Static frontend ----------
if os.path.isdir("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

    @app.get("/")
    def root():
        return FileResponse("static/index.html")
