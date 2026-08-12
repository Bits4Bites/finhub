"""Unit tests for the asynchronous cache utility."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.utils import cache


def test_generate_key_is_deterministic_and_order_sensitive():
    assert cache.generate_key("alpha", "beta") == cache.generate_key("alpha", "beta")
    assert cache.generate_key("alpha", "beta") != cache.generate_key("beta", "alpha")


def test_generate_key_preserves_item_boundaries():
    assert cache.generate_key("ab", "c") != cache.generate_key("a", "bc")


def test_generate_key_includes_application_version():
    original_key = cache.generate_key("alpha")

    with patch("app.utils.cache.version.VERSION", "next-version"):
        versioned_key = cache.generate_key("alpha")

    assert versioned_key != original_key


def test_cache_entry_expires():
    async def scenario():
        await cache.clear()

        assert await cache.set("quote:AAPL", {"price": 210}, ttl=0.01)
        assert await cache.get("quote:AAPL") == {"price": 210}
        assert await cache.exists("quote:AAPL")

        await asyncio.sleep(0.02)

        assert await cache.get("quote:AAPL", default="missing") == "missing"
        assert not await cache.exists("quote:AAPL")

    asyncio.run(scenario())


def test_cache_delete_and_clear():
    async def scenario():
        await cache.clear()
        await cache.set("first", 1, ttl=60)
        await cache.set("second", 2, ttl=60)

        assert await cache.delete("first")
        assert not await cache.delete("first")
        assert await cache.get("first") is None

        assert await cache.clear()
        assert await cache.get("second") is None

    asyncio.run(scenario())


@pytest.mark.parametrize("ttl", [0, -1])
def test_cache_uses_default_for_invalid_ttl(ttl):
    with patch("app.utils.cache._cache.set", new_callable=AsyncMock, return_value=True) as mock_set:
        asyncio.run(cache.set("key", "value", ttl=ttl))

    mock_set.assert_awaited_once_with("key", "value", ttl=3600)


def test_cache_set_defaults_to_one_hour():
    with patch("app.utils.cache._cache.set", new_callable=AsyncMock, return_value=True) as mock_set:
        asyncio.run(cache.set("key", "value"))

    mock_set.assert_awaited_once_with("key", "value", ttl=3600)
