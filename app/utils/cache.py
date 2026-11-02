"""Asynchronous in-memory cache with expiring entries."""

import re
from datetime import UTC, datetime
from typing import Any

import xxhash
from aiocache import SimpleMemoryCache

from .. import version

__all__ = ["clear", "delete", "exists", "generate_hourly_key", "generate_key", "get", "set"]

_DEFAULT_TTL = 3600
_ISO_DATETIME_PATTERN = re.compile(
    r"(?<!\d)"
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?"
    r"(?:Z|[+-]\d{2}:\d{2})"
    r"(?!\d)"
)
_cache = SimpleMemoryCache()


def generate_key(*items: str) -> str:
    """Generate a version-aware XXH3-128 cache key from arbitrary strings."""
    hasher = xxhash.xxh3_128()
    for item in (version.VERSION, *items):
        encoded_item = item.encode()
        hasher.update(len(encoded_item).to_bytes(8, byteorder="big"))
        hasher.update(encoded_item)
    return hasher.hexdigest()


def generate_hourly_key(*items: str) -> str:
    """Generate a cache key after normalizing embedded ISO datetimes to UTC hours."""
    return generate_key(*(_ISO_DATETIME_PATTERN.sub(_normalize_datetime_hour, item) for item in items))


def _normalize_datetime_hour(match: re.Match[str]) -> str:
    try:
        value = datetime.fromisoformat(match.group().replace("Z", "+00:00"))
    except ValueError:
        return match.group()
    hourly_value = value.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    return hourly_value.isoformat(timespec="seconds").replace("+00:00", "Z")


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
