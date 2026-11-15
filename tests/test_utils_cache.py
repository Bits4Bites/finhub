"""Unit tests for the asynchronous cache utility."""

import asyncio

import pytest

from app import version
from app.utils import cache


@pytest.fixture(autouse=True)
def reset_cache():
    asyncio.run(cache.clear())
    yield
    asyncio.run(cache.clear())


def test_generate_key_is_deterministic_and_preserves_component_identity():
    assert cache.generate_key("alpha", "beta") == cache.generate_key("alpha", "beta")
    assert cache.generate_key("alpha", "beta") != cache.generate_key("beta", "alpha")
    assert cache.generate_key("ab", "c") != cache.generate_key("a", "bc")


def test_generate_key_changes_with_the_application_version(monkeypatch):
    original_key = cache.generate_key("alpha")

    monkeypatch.setattr(version, "VERSION", "next-version")

    assert cache.generate_key("alpha") != original_key


def test_generate_hourly_key_groups_datetimes_within_the_same_utc_hour():
    first = '{"as_of":"2026-08-23T16:10:18Z","references":[{"accessed_at":"2026-08-23T18:45:00+00:00"}]}'
    second = '{"as_of":"2026-08-23T16:59:59+00:00","references":[{"accessed_at":"2026-08-23T18:01:00Z"}]}'

    assert cache.generate_hourly_key(first) == cache.generate_hourly_key(second)


def test_generate_hourly_key_uses_utc_hour_boundaries():
    utc_value = '{"as_of":"2026-08-23T16:10:00Z"}'
    offset_value = '{"as_of":"2026-08-23T18:50:00+02:00"}'
    next_hour = '{"as_of":"2026-08-23T17:00:00Z"}'

    assert cache.generate_hourly_key(utc_value) == cache.generate_hourly_key(offset_value)
    assert cache.generate_hourly_key(utc_value) != cache.generate_hourly_key(next_hour)


def test_generate_hourly_key_requires_seconds_and_a_timezone():
    first = '{"as_of":"2026-08-23T16:10Z"}'
    second = '{"as_of":"2026-08-23T16:20Z"}'

    assert cache.generate_hourly_key(first) != cache.generate_hourly_key(second)


def test_generate_hourly_key_preserves_non_temporal_key_behavior():
    items = ("portfolio", '{"positions":[{"ticker":"NASDAQ:AAPL","weight":0.6}]}')

    assert cache.generate_hourly_key(*items) == cache.generate_key(*items)


def test_cache_stores_and_retrieves_values():
    async def scenario():
        value = {"price": 210}

        assert await cache.set("quote:AAPL", value, ttl=60)
        assert await cache.get("quote:AAPL") == value
        assert await cache.exists("quote:AAPL")
        assert await cache.get("quote:MSFT", default="missing") == "missing"

    asyncio.run(scenario())


def test_cache_preserves_none_as_a_stored_value():
    async def scenario():
        assert await cache.set("nullable", None, ttl=60)
        assert await cache.exists("nullable")
        assert await cache.get("nullable", default="missing") is None
        assert await cache.delete("nullable")
        assert not await cache.exists("nullable")

    asyncio.run(scenario())


def test_cache_entry_expires():
    async def scenario():
        assert await cache.set("quote:AAPL", {"price": 210}, ttl=0.05)

        await asyncio.sleep(0.1)

        assert await cache.get("quote:AAPL", default="missing") == "missing"
        assert not await cache.exists("quote:AAPL")

    asyncio.run(scenario())


def test_cache_delete_reports_whether_the_entry_existed():
    async def scenario():
        assert await cache.set("key", "value", ttl=60)

        assert await cache.delete("key")
        assert not await cache.delete("key")
        assert await cache.get("key", default="missing") == "missing"

    asyncio.run(scenario())


def test_cache_clear_removes_all_values():
    async def scenario():
        assert await cache.set("first", 1, ttl=60)
        assert await cache.set("second", 2, ttl=60)

        assert await cache.clear()
        assert await cache.get("first", default="missing") == "missing"
        assert await cache.get("second", default="missing") == "missing"

    asyncio.run(scenario())


@pytest.mark.parametrize("ttl", [0, -1])
def test_cache_uses_default_lifetime_for_non_positive_ttl(ttl):
    async def scenario():
        assert await cache.set("key", "value", ttl=ttl)

        await asyncio.sleep(0.02)

        assert await cache.get("key") == "value"

    asyncio.run(scenario())


def test_cache_uses_default_lifetime_when_ttl_is_omitted():
    async def scenario():
        assert await cache.set("key", "value")

        await asyncio.sleep(0.02)

        assert await cache.get("key") == "value"

    asyncio.run(scenario())


def test_clearing_cache_prevents_old_expiry_from_deleting_a_reused_key():
    async def scenario():
        assert await cache.set("key", "old", ttl=0.1)
        assert await cache.clear()
        assert await cache.set("key", "new", ttl=1)

        await asyncio.sleep(0.15)

        assert await cache.get("key") == "new"

    asyncio.run(scenario())
