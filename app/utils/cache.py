"""Asynchronous in-memory cache with expiring entries."""

from typing import Any

from aiocache import SimpleMemoryCache

__all__ = ["clear", "delete", "exists", "get", "set"]

_DEFAULT_TTL = 3600
_cache = SimpleMemoryCache()


async def get(key: str, default: Any = None) -> Any:
    """Return a cached value, or the default when the key is absent or expired."""
    return await _cache.get(key, default=default)


async def set(key: str, value: Any, ttl: float = _DEFAULT_TTL) -> bool:
    """Cache a value, using the one-hour default when TTL is non-positive."""
    if ttl <= 0:
        ttl = _DEFAULT_TTL
    return await _cache.set(key, value, ttl=ttl)


async def exists(key: str) -> bool:
    """Return whether an unexpired value exists for the key."""
    return await _cache.exists(key)


async def delete(key: str) -> bool:
    """Delete a cached value and return whether it existed."""
    return bool(await _cache.delete(key))


async def clear() -> bool:
    """Delete all cached values."""
    return await _cache.clear()
