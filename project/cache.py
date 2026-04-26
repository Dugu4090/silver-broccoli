"""Simple disk-backed cache for LLM + embedding calls."""
import hashlib
import json
import diskcache

_cache = diskcache.Cache("./.cache")


def _key(prefix: str, *parts) -> str:
    h = hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()
    return f"{prefix}:{h}"


def get(prefix: str, *parts):
    return _cache.get(_key(prefix, *parts))


def put(prefix: str, *parts, value, ttl: int = 60 * 60 * 24 * 7):
    _cache.set(_key(prefix, *parts), value, expire=ttl)
    return value
