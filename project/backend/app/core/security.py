from datetime import datetime, timedelta, timezone
from passlib.context import CryptContext
from jose import jwt, JWTError
from app.config import settings

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
ALG = "HS256"


def hash_password(p: str) -> str:
    return pwd_ctx.hash(p)


def verify_password(p: str, h: str) -> bool:
    return pwd_ctx.verify(p, h)


def _now():
    return datetime.now(timezone.utc)


def create_access_token(sub: str, role: str) -> str:
    payload = {
        "sub": sub, "role": role, "type": "access",
        "exp": _now() + timedelta(minutes=settings.JWT_ACCESS_MIN),
        "iat": _now(),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=ALG)


def create_refresh_token(sub: str) -> str:
    payload = {
        "sub": sub, "type": "refresh",
        "exp": _now() + timedelta(days=settings.JWT_REFRESH_DAYS),
        "iat": _now(),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=ALG)


def decode(token: str) -> dict:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[ALG])
    except JWTError as e:
        raise ValueError(f"Invalid token: {e}")
