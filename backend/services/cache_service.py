"""
Redis Cache Service — response caching for expensive analytics endpoints.

Falls back to an in-memory LRU dict when Redis is not available.
TTL is configurable per cache key; default is 5 minutes.

Usage:
    cache = CacheService()

    # Get or compute
    result = await cache.get_or_set("key", compute_fn, ttl=300)

    # Manual set / get
    cache.set("key", value, ttl=60)
    cache.get("key")          # None if missing/expired
    cache.delete("key")
    cache.invalidate_prefix("analytics:dataset_id")
"""

import os
import json
import time
import logging
import hashlib
from typing import Any, Callable, Optional
from collections import OrderedDict

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CACHE_ENABLED = os.getenv("CACHE_ENABLED", "true").lower() == "true"
DEFAULT_TTL = int(os.getenv("CACHE_DEFAULT_TTL", "300"))   # 5 minutes
MAX_MEMORY_ITEMS = 512


# ── In-memory fallback ────────────────────────────────────────────

class _MemoryCache:
    """Simple LRU dict with TTL — used when Redis is unavailable."""

    def __init__(self, max_size: int = MAX_MEMORY_ITEMS):
        self._store: OrderedDict = OrderedDict()
        self.max_size = max_size

    def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if time.time() > expires_at:
            del self._store[key]
            return None
        # Move to end (LRU)
        self._store.move_to_end(key)
        return value

    def set(self, key: str, value: Any, ttl: int = DEFAULT_TTL):
        if key in self._store:
            self._store.move_to_end(key)
        self._store[key] = (value, time.time() + ttl)
        if len(self._store) > self.max_size:
            self._store.popitem(last=False)

    def delete(self, key: str):
        self._store.pop(key, None)

    def keys_with_prefix(self, prefix: str):
        return [k for k in self._store if k.startswith(prefix)]


# ── Redis client (lazy init) ─────────────────────────────────────

_redis_client = None

def _get_redis():
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    try:
        import redis
        client = redis.from_url(REDIS_URL, socket_connect_timeout=2, socket_timeout=2)
        client.ping()
        _redis_client = client
        logger.info("Cache: Redis connected")
    except Exception as e:
        logger.info(f"Cache: Redis unavailable ({e}) — using in-memory fallback")
        _redis_client = None
    return _redis_client


# ── Main CacheService ────────────────────────────────────────────

class CacheService:
    """
    Unified caching interface — uses Redis when available,
    falls back to in-memory LRU cache.
    """

    def __init__(self):
        self._memory = _MemoryCache()

    # ── Low-level ops ────────────────────────────────────────────

    def get(self, key: str) -> Optional[Any]:
        if not CACHE_ENABLED:
            return None
        r = _get_redis()
        if r:
            try:
                raw = r.get(key)
                return json.loads(raw) if raw else None
            except Exception:
                pass
        return self._memory.get(key)

    def set(self, key: str, value: Any, ttl: int = DEFAULT_TTL):
        if not CACHE_ENABLED:
            return
        r = _get_redis()
        if r:
            try:
                r.setex(key, ttl, json.dumps(value, default=str))
                return
            except Exception:
                pass
        self._memory.set(key, value, ttl)

    def delete(self, key: str):
        r = _get_redis()
        if r:
            try:
                r.delete(key)
            except Exception:
                pass
        self._memory.delete(key)

    def invalidate_prefix(self, prefix: str):
        """Delete all cache entries whose key starts with `prefix`."""
        r = _get_redis()
        if r:
            try:
                keys = r.keys(f"{prefix}*")
                if keys:
                    r.delete(*keys)
                return
            except Exception:
                pass
        for key in self._memory.keys_with_prefix(prefix):
            self._memory.delete(key)

    # ── Higher-level helpers ─────────────────────────────────────

    def get_or_set(self, key: str, compute_fn: Callable, ttl: int = DEFAULT_TTL) -> Any:
        """Return cached value or compute, cache, and return it."""
        cached = self.get(key)
        if cached is not None:
            logger.debug(f"Cache HIT: {key}")
            return cached
        logger.debug(f"Cache MISS: {key}")
        result = compute_fn()
        self.set(key, result, ttl)
        return result

    @staticmethod
    def make_key(*parts) -> str:
        """Build a deterministic cache key from parts."""
        raw = ":".join(str(p) for p in parts)
        return hashlib.md5(raw.encode()).hexdigest()[:16] + ":" + raw[:80]


# ── Singleton ────────────────────────────────────────────────────
cache = CacheService()
