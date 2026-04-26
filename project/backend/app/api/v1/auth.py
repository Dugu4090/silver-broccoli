import uuid
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models import User, RefreshToken
from app.schemas.auth import SignupIn, LoginIn, TokenPair, RefreshIn, UserOut
from app.core.security import hash_password, verify_password, create_access_token, create_refresh_token, decode
from app.config import settings
from app.deps import get_current_user

router = APIRouter()


@router.post("/signup", response_model=TokenPair)
async def signup(payload: SignupIn, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(User).where(User.email == payload.email))
    if res.scalar_one_or_none():
        raise HTTPException(400, "Email already registered")
    role = payload.role if payload.role in ("student", "teacher", "parent") else "student"
    u = User(
        email=payload.email, hashed_password=hash_password(payload.password),
        full_name=payload.full_name, grade=payload.grade,
        language=payload.language, role=role,
    )
    db.add(u); await db.commit(); await db.refresh(u)
    return await _issue_tokens(db, u)


@router.post("/login", response_model=TokenPair)
async def login(payload: LoginIn, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(User).where(User.email == payload.email))
    u = res.scalar_one_or_none()
    if not u or not verify_password(payload.password, u.hashed_password):
        raise HTTPException(401, "Bad email or password")
    return await _issue_tokens(db, u)


@router.post("/refresh", response_model=TokenPair)
async def refresh(payload: RefreshIn, db: AsyncSession = Depends(get_db)):
    try:
        data = decode(payload.refresh_token)
    except ValueError as e:
        raise HTTPException(401, str(e))
    if data.get("type") != "refresh":
        raise HTTPException(401, "Wrong token type")
    res = await db.execute(select(User).where(User.email == data["sub"]))
    u = res.scalar_one_or_none()
    if not u:
        raise HTTPException(401, "User not found")
    return await _issue_tokens(db, u)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return user


async def _issue_tokens(db: AsyncSession, u: User) -> TokenPair:
    access = create_access_token(u.email, u.role)
    refresh_tok = create_refresh_token(u.email)
    rt = RefreshToken(
        user_id=u.id, jti=str(uuid.uuid4()),
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_DAYS),
    )
    db.add(rt); await db.commit()
    return TokenPair(access_token=access, refresh_token=refresh_tok)
