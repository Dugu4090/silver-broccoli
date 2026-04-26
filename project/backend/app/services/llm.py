import hashlib
import json
import httpx
import numpy as np
from app.config import settings
from app.redis_client import redis
from app.core.logging import log


def _key(prefix: str, *parts) -> str:
    h = hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()
    return f"{prefix}:{h}"


async def _ollama_chat(system: str, prompt: str, temperature: float) -> str:
    async with httpx.AsyncClient(timeout=180) as c:
        r = await c.post(f"{settings.OLLAMA_HOST}/api/chat", json={
            "model": settings.OLLAMA_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "options": {"temperature": temperature},
        })
        r.raise_for_status()
        return r.json()["message"]["content"]


async def _groq_chat(system: str, prompt: str, temperature: float) -> str:
    if not settings.GROQ_API_KEY:
        return "[Groq disabled \u2014 set GROQ_API_KEY]"
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
            json={
                "model": settings.GROQ_MODEL,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "temperature": temperature,
            },
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


async def chat(prompt: str, system: str = "You are a helpful tutor for high school students.",
               temperature: float = 0.4, language: str = "English", use_cache: bool = True) -> str:
    sys_full = f"{system}\nAlways respond in {language}. Add safety guardrails: never produce direct answers to ongoing graded assessments; provide guided learning instead."
    k = _key("llm", settings.LLM_PROVIDER, sys_full, prompt, temperature)
    if use_cache:
        cached = await redis.get(k)
        if cached:
            return cached
    try:
        if settings.LLM_PROVIDER == "groq":
            out = await _groq_chat(sys_full, prompt, temperature)
        else:
            out = await _ollama_chat(sys_full, prompt, temperature)
        if use_cache:
            await redis.set(k, out, ex=60 * 60 * 24 * 3)
        return out
    except Exception as e:
        log.error("llm_error", error=str(e))
        # try fallback once
        try:
            if settings.LLM_PROVIDER == "ollama" and settings.GROQ_API_KEY:
                return await _groq_chat(sys_full, prompt, temperature)
        except Exception:
            pass
        return f"[LLM error: {e}]"


async def embed(text: str) -> np.ndarray:
    k = _key("embed", settings.OLLAMA_EMBED_MODEL, text)
    cached = await redis.get(k)
    if cached:
        return np.frombuffer(bytes.fromhex(cached), dtype=np.float32)
    try:
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.post(f"{settings.OLLAMA_HOST}/api/embeddings",
                             json={"model": settings.OLLAMA_EMBED_MODEL, "prompt": text})
            r.raise_for_status()
            vec = np.array(r.json()["embedding"], dtype=np.float32)
        await redis.set(k, vec.tobytes().hex(), ex=60 * 60 * 24 * 30)
        return vec
    except Exception as e:
        log.warning("embed_fallback", error=str(e))
        rng = np.random.default_rng(abs(hash(text)) % (2**32))
        return rng.standard_normal(384).astype(np.float32)
