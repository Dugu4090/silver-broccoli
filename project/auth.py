import os
from datetime import datetime, timedelta, date
from passlib.context import CryptContext
from jose import jwt, JWTError
from db import SessionLocal, User

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret")
JWT_ALG = "HS256"
JWT_EXP_MIN = 60 * 24 * 7

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(p: str) -> str:
    return pwd_ctx.hash(p)


def verify_password(p: str, h: str) -> bool:
    return pwd_ctx.verify(p, h)


def create_token(email: str) -> str:
    payload = {"sub": email, "exp": datetime.utcnow() + timedelta(minutes=JWT_EXP_MIN)}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def _update_streak(user: User, db):
    today = date.today()
    last = user.last_active or today
    if last == today:
        return
    if (today - last).days == 1:
        user.streak_count = (user.streak_count or 0) + 1
    else:
        user.streak_count = 1
    user.last_active = today
    db.commit()


def user_from_token(token: str):
    if not token:
        return None
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        email = payload.get("sub")
    except JWTError:
        return None
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.email == email).first()
        if u:
            _update_streak(u, db)
        return u
    finally:
        db.close()


def signup(email: str, password: str, grade: str = "", language: str = "English"):
    db = SessionLocal()
    try:
        if db.query(User).filter(User.email == email).first():
            raise ValueError("Email already registered")
        u = User(
            email=email, hashed_password=hash_password(password),
            grade=grade or "", language=language or "English", role="student",
        )
        db.add(u); db.commit(); db.refresh(u)
        return create_token(u.email)
    finally:
        db.close()


def login(email: str, password: str):
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.email == email).first()
        if not u or not verify_password(password, u.hashed_password):
            raise ValueError("Bad email or password")
        return create_token(u.email)
    finally:
        db.close()
