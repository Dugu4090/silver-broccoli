"""Unified LLM + embeddings client with caching."""
import os
import httpx
import numpy as np
import cache
from logging_config import log

PROVIDER = os.getenv("LLM_PROVIDER", "ollama").lower()
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
DEFAULT_LANGUAGE = os.getenv("DEFAULT_LANGUAGE", "English")


def _ollama(system: str, prompt: str, temperature: float) -> str:
    r = httpx.post(
        f"{OLLAMA_HOST}/api/chat",
        json={
            "model": OLLAMA_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "options": {"temperature": temperature},
        },
        timeout=180,
    )
    r.raise_for_status()
    return r.json()["message"]["content"]


def _groq(system: str, prompt: str, temperature: float) -> str:
    if not GROQ_API_KEY:
        return "[Groq disabled \u2014 set GROQ_API_KEY]"
    r = httpx.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
        json={
            "model": GROQ_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
        },
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def llm(prompt: str, system: str = "You are a helpful tutor for high school students.",
        temperature: float = 0.5, language: str = None, use_cache: bool = True) -> str:
    language = language or DEFAULT_LANGUAGE
    system_full = f"{system}\nAlways respond in {language}."
    if use_cache:
        cached = cache.get("llm", PROVIDER, system_full, prompt, temperature)
        if cached:
            return cached
    try:
        out = _groq(system_full, prompt, temperature) if PROVIDER == "groq" else _ollama(system_full, prompt, temperature)
        if use_cache:
            cache.put("llm", PROVIDER, system_full, prompt, temperature, value=out)
        return out
    except Exception as e:
        log.exception("LLM error")
        return f"[LLM error: {e}]"


def embed(text: str) -> np.ndarray:
    """Get embedding via Ollama. Returns float32 numpy array."""
    cached = cache.get("embed", OLLAMA_EMBED_MODEL, text)
    if cached is not None:
        return np.frombuffer(cached, dtype=np.float32)
    try:
        r = httpx.post(
            f"{OLLAMA_HOST}/api/embeddings",
            json={"model": OLLAMA_EMBED_MODEL, "prompt": text},
            timeout=60,
        )
        r.raise_for_status()
        vec = np.array(r.json()["embedding"], dtype=np.float32)
        cache.put("embed", OLLAMA_EMBED_MODEL, text, value=vec.tobytes())
        return vec
    except Exception as e:
        log.warning(f"Embedding fallback (hash-based): {e}")
        # deterministic fallback so app still works without embed model
        rng = np.random.default_rng(abs(hash(text)) % (2**32))
        return rng.standard_normal(384).astype(np.float32)
