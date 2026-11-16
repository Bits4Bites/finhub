"""Asynchronous in-memory cache with expiring entries."""

import dataclasses
import re
import time
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


@dataclasses.dataclass(frozen=True, slots=True)
class _CacheEntry:
    value: Any
    expires_at: float


_cache = SimpleMemoryCache()


def generate_key(*items: str) -> str:
    """Create an opaque cache identity for versioned business inputs.

    Args:
        items: Ordered string components that identify the cached result.

    Returns:
        A deterministic key in the current application-version namespace.

    Notes:
        Repeating the same ordered components produces the same key. Different
        component values, order, or application versions represent separate
        cache entries.
    """
    hasher = xxhash.xxh3_128()
    for item in (version.VERSION, *items):
        encoded_item = item.encode()
        hasher.update(len(encoded_item).to_bytes(8, byteorder="big"))
        hasher.update(encoded_item)
    return hasher.hexdigest()


def generate_hourly_key(*items: str) -> str:
    """Generate a cache key that groups timestamped inputs by UTC hour.

    Args:
        items: Ordered string components that may contain timezone-qualified ISO
            8601 datetimes.

    Returns:
        A version-scoped cache key with recognized datetimes grouped into their
        UTC hour.

    Notes:
        Datetimes must include seconds and either ``Z`` or a numeric UTC offset.
        Components without recognized datetimes behave like ``generate_key``.
    """
    return generate_key(*(_ISO_DATETIME_PATTERN.sub(_normalize_datetime_hour, item) for item in items))


def _normalize_datetime_hour(match: re.Match[str]) -> str:
    try:
        value = datetime.fromisoformat(match.group().replace("Z", "+00:00"))
    except ValueError:
        return match.group()
    hourly_value = value.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    return hourly_value.isoformat(timespec="seconds").replace("+00:00", "Z")


async def get(key: str, default: Any = None) -> Any:
    """Retrieve an unexpired value from the application cache.

    Args:
        key: The cache key identifying the stored value.
        default: The value returned when the key is absent or expired.

    Returns:
        The cached value, including a cached ``None``, or ``default`` when no
        unexpired entry exists.
    """
    entry = await _cache.get(key)
    if not isinstance(entry, _CacheEntry):
        return default
    if time.monotonic() >= entry.expires_at:
        await _cache.delete(key)
        return default
    return entry.value


async def set(key: str, value: Any, ttl: float = _DEFAULT_TTL) -> bool:
    """Store a value in the application cache for a limited time.

    Args:
        key: The cache key identifying the value.
        value: The value to cache.
        ttl: Lifetime in seconds. The one-hour default is used when the supplied
            value is non-positive.

    Returns:
        ``True`` when the value is stored successfully.

    Notes:
        The value becomes unavailable when its full lifetime has elapsed.
    """
    if ttl <= 0:
        ttl = _DEFAULT_TTL
    return await _cache.set(
        key,
        _CacheEntry(value=value, expires_at=time.monotonic() + ttl),
        ttl=ttl,
    )


async def exists(key: str) -> bool:
    """Check whether an unexpired cache entry exists.

    Args:
        key: The cache key to check.

    Returns:
        ``True`` when an unexpired entry exists; otherwise ``False``.
    """
    missing = object()
    return await get(key, missing) is not missing


async def delete(key: str) -> bool:
    """Delete one value from the application cache.

    Args:
        key: The cache key to delete.

    Returns:
        ``True`` when an entry was deleted; otherwise ``False``.
    """
    if not await exists(key):
        return False
    return bool(await _cache.delete(key))


async def clear() -> bool:
    """Delete every value from the application cache.

    Returns:
        ``True`` when the cache is cleared successfully.

    Notes:
        Values written after a clear are independent of the lifetimes assigned
        to removed entries.
    """
    global _cache

    cache_to_clear = _cache
    _cache = SimpleMemoryCache()
    return await cache_to_clear.clear()
