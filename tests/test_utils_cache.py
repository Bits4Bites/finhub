"""Black-box tests for the asynchronous cache utility."""

import asyncio
import types

import pytest

from app import version
from app.utils import cache


class _Clock:
    def __init__(self):
        self.current = 1_000.0

    def __call__(self) -> float:
        return self.current

    def advance(self, seconds: float) -> None:
        self.current += seconds


@pytest.fixture(autouse=True)
def reset_cache():
    asyncio.run(cache.clear())
    yield
    asyncio.run(cache.clear())


@pytest.fixture
def clock(monkeypatch):
    controlled_clock = _Clock()
    monkeypatch.setattr(
        cache,
        "time",
        types.SimpleNamespace(monotonic=controlled_clock),
    )
    return controlled_clock


def test_generated_key_reopens_the_same_business_cache_entry(clock):
    async def scenario():
        await cache.set(cache.generate_key("quote", "NASDAQ:AAPL"), {"price": 210})

        assert await cache.get(cache.generate_key("quote", "NASDAQ:AAPL")) == {
            "price": 210,
        }

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("stored_identity", "other_identity"),
    [
        (("quote", "NASDAQ:AAPL"), ("quote", "NASDAQ:MSFT")),
        (("portfolio", "growth", "balanced"), ("portfolio", "balanced", "growth")),
        (("portfolio", "ab", "c"), ("portfolio", "a", "bc")),
    ],
)
def test_generated_keys_keep_distinct_business_inputs_separate(
    stored_identity,
    other_identity,
    clock,
):
    async def scenario():
        await cache.set(cache.generate_key(*stored_identity), "stored")

        assert await cache.get(cache.generate_key(*other_identity), default="missing") == "missing"

    asyncio.run(scenario())


def test_generated_keys_use_the_application_version_as_a_namespace(
    monkeypatch,
    clock,
):
    async def scenario():
        await cache.set(cache.generate_key("quote", "NASDAQ:AAPL"), "current")

        monkeypatch.setattr(version, "VERSION", "next-version")

        assert (
            await cache.get(
                cache.generate_key("quote", "NASDAQ:AAPL"),
                default="missing",
            )
            == "missing"
        )

    asyncio.run(scenario())


def test_hourly_keys_share_entries_within_the_same_utc_hour(clock):
    first = '{"as_of":"2026-08-23T16:10:18Z","accessed_at":"2026-08-23T18:45:00+00:00"}'
    equivalent = '{"as_of":"2026-08-23T18:59:59+02:00","accessed_at":"2026-08-23T18:01:00Z"}'

    async def scenario():
        await cache.set(cache.generate_hourly_key(first), "hourly result")

        assert await cache.get(cache.generate_hourly_key(equivalent)) == "hourly result"

    asyncio.run(scenario())


def test_hourly_keys_separate_utc_hour_boundaries(clock):
    current_hour = '{"as_of":"2026-08-23T16:59:59Z"}'
    next_hour = '{"as_of":"2026-08-23T17:00:00Z"}'

    async def scenario():
        await cache.set(cache.generate_hourly_key(current_hour), "current")

        assert (
            await cache.get(
                cache.generate_hourly_key(next_hour),
                default="missing",
            )
            == "missing"
        )

    asyncio.run(scenario())


def test_hourly_keys_leave_incomplete_timestamps_distinct(clock):
    first = '{"as_of":"2026-08-23T16:10Z"}'
    second = '{"as_of":"2026-08-23T16:20Z"}'

    async def scenario():
        await cache.set(cache.generate_hourly_key(first), "first")

        assert (
            await cache.get(
                cache.generate_hourly_key(second),
                default="missing",
            )
            == "missing"
        )

    asyncio.run(scenario())


def test_hourly_keys_preserve_non_temporal_cache_identity(clock):
    items = ("portfolio", '{"positions":[{"ticker":"NASDAQ:AAPL","weight":0.6}]}')

    async def scenario():
        await cache.set(cache.generate_key(*items), "portfolio")

        assert await cache.get(cache.generate_hourly_key(*items)) == "portfolio"

    asyncio.run(scenario())


def test_cache_stores_values_and_reports_missing_entries(clock):
    async def scenario():
        value = {"price": 210}

        assert await cache.set("quote:AAPL", value, ttl=60)
        assert await cache.get("quote:AAPL") == value
        assert await cache.exists("quote:AAPL")
        assert await cache.get("quote:MSFT", default="missing") == "missing"
        assert not await cache.exists("quote:MSFT")

    asyncio.run(scenario())


def test_cache_preserves_none_as_a_stored_value(clock):
    async def scenario():
        assert await cache.set("nullable", None, ttl=60)
        assert await cache.exists("nullable")
        assert await cache.get("nullable", default="missing") is None

    asyncio.run(scenario())


def test_cache_expiry_uses_the_supplied_lifetime(clock):
    async def scenario():
        assert await cache.set("quote:AAPL", {"price": 210}, ttl=60)

        clock.advance(59.999)
        assert await cache.exists("quote:AAPL")
        assert await cache.get("quote:AAPL") == {"price": 210}

        clock.advance(0.001)
        assert await cache.get("quote:AAPL", default="missing") == "missing"
        assert not await cache.exists("quote:AAPL")

    asyncio.run(scenario())


def test_cache_delete_reports_public_entry_state(clock):
    async def scenario():
        assert await cache.set("key", "value", ttl=60)

        assert await cache.delete("key")
        assert not await cache.delete("key")
        assert await cache.get("key", default="missing") == "missing"

    asyncio.run(scenario())


def test_cache_clear_removes_all_values(clock):
    async def scenario():
        assert await cache.set("first", 1, ttl=60)
        assert await cache.set("second", 2, ttl=60)

        assert await cache.clear()
        assert await cache.get("first", default="missing") == "missing"
        assert await cache.get("second", default="missing") == "missing"
        assert not await cache.exists("first")
        assert not await cache.exists("second")

    asyncio.run(scenario())


@pytest.mark.parametrize("ttl", [None, 0, -1])
def test_cache_uses_a_one_hour_default_lifetime(ttl, clock):
    async def scenario():
        if ttl is None:
            assert await cache.set("key", "value")
        else:
            assert await cache.set("key", "value", ttl=ttl)

        clock.advance(3_599.999)
        assert await cache.get("key") == "value"
        assert await cache.exists("key")

        clock.advance(0.001)
        assert await cache.get("key", default="missing") == "missing"
        assert not await cache.exists("key")

    asyncio.run(scenario())


def test_clearing_cache_keeps_a_reused_key_independent(
    clock,
    monkeypatch,
):
    async def scenario():
        loop = asyncio.get_running_loop()
        monkeypatch.setattr(loop, "time", clock)

        assert await cache.set("key", "old", ttl=10)
        assert await cache.clear()
        assert await cache.set("key", "new", ttl=100)

        clock.advance(10)
        await asyncio.sleep(0)

        assert await cache.get("key") == "new"
        assert await cache.exists("key")

    asyncio.run(scenario())
