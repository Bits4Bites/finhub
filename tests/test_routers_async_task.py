import asyncio
from unittest import mock

import pytest
from fastapi import HTTPException

from app.routers import async_task as router_async_task
from app.schemas import async_task as schemas_async_task
from app.schemas import base_req_resp

_EXPIRY_TTL_SECONDS = 10.0
_BEFORE_EXPIRY_SECONDS = 9.0
_PAST_EXPIRY_SECONDS = 2.0
_PAST_RESET_EXPIRY_SECONDS = 9.0


class _ControllableTaskCache:
    def __init__(self):
        self._now = 0.0
        self._entries: dict[str, tuple[object, float]] = {}

    async def get(self, key: str, default: object = None) -> object:
        entry = self._entries.get(key)
        if entry is None:
            return default
        value, expires_at = entry
        if self._now >= expires_at:
            self._entries.pop(key, None)
            return default
        return value

    async def set(self, key: str, value: object, ttl: float) -> bool:
        self._entries[key] = (value, self._now + ttl)
        return True

    def advance(self, seconds: float) -> None:
        self._now += seconds


@pytest.fixture(autouse=True)
def clear_task_cache():
    asyncio.run(router_async_task.cache.clear())
    yield
    asyncio.run(router_async_task.cache.clear())


@pytest.fixture
def controllable_task_cache(monkeypatch):
    task_cache = _ControllableTaskCache()
    monkeypatch.setattr(router_async_task.cache, "get", task_cache.get)
    monkeypatch.setattr(router_async_task.cache, "set", task_cache.set)
    monkeypatch.setattr(schemas_async_task, "ASYNC_TASK_TTL", _EXPIRY_TTL_SECONDS)
    return task_cache


def test_start_task_persists_a_loadable_running_entry():
    async def run_scenario():
        task_id, is_new = await router_async_task.start_task("example", "input")
        return task_id, is_new, await router_async_task.load_task(task_id, "example")

    task_id, is_new, task_entry = asyncio.run(run_scenario())

    assert task_id
    assert is_new is True
    assert isinstance(task_entry, router_async_task.TaskEntry)
    assert task_entry.state == schemas_async_task.TASK_STATE_RUNNING
    assert task_entry.status is None
    assert task_entry.message is None
    assert task_entry.result is None


def test_start_task_deduplicates_concurrent_identical_inputs():
    async def run_scenario():
        starts = await asyncio.gather(
            router_async_task.start_task("example", "same-input"),
            router_async_task.start_task("example", "same-input"),
        )
        task_entry = await router_async_task.load_task(starts[0][0], "example")
        return starts, task_entry

    starts, task_entry = asyncio.run(run_scenario())

    assert starts[0][0] == starts[1][0]
    assert sorted(is_new for _, is_new in starts) == [False, True]
    assert task_entry.state == schemas_async_task.TASK_STATE_RUNNING


def test_start_task_expires_after_the_configured_lifetime(controllable_task_cache):
    async def run_scenario():
        task_id, _ = await router_async_task.start_task("example", "expiring-start")
        controllable_task_cache.advance(_BEFORE_EXPIRY_SECONDS)
        before_expiry = await router_async_task.load_task(task_id, "example")
        controllable_task_cache.advance(_PAST_EXPIRY_SECONDS)
        with pytest.raises(HTTPException) as exc_info:
            await router_async_task.load_task(task_id, "example")
        return before_expiry, exc_info.value.status_code

    before_expiry, expired_status = asyncio.run(run_scenario())

    assert before_expiry.state == schemas_async_task.TASK_STATE_RUNNING
    assert expired_status == 404


@pytest.mark.parametrize(
    "state",
    [
        schemas_async_task.TASK_STATE_RUNNING,
        schemas_async_task.TASK_STATE_COMPLETED,
        schemas_async_task.TASK_STATE_FAILED,
    ],
)
def test_start_task_deduplicates_running_and_terminal_entries(state):
    result = base_req_resp.BaseResponse[str](status=200, message="ok", data="done")

    async def run_scenario():
        task_id, _ = await router_async_task.start_task("example", "same-input")
        if state == schemas_async_task.TASK_STATE_COMPLETED:
            await router_async_task.complete_task(task_id, "example", result)
        elif state == schemas_async_task.TASK_STATE_FAILED:
            await router_async_task.fail_task(task_id, "example", status_code=502, message="failed")

        duplicate_id, is_new = await router_async_task.start_task("example", "same-input")
        task_entry = await router_async_task.load_task(task_id, "example")
        return task_id, duplicate_id, is_new, task_entry

    task_id, duplicate_id, is_new, task_entry = asyncio.run(run_scenario())

    assert duplicate_id == task_id
    assert is_new is False
    assert task_entry.state == state


def test_complete_task_round_trips_result_and_optional_metadata():
    result = base_req_resp.BaseResponse[str](status=200, message="ok", data="done")

    async def run_scenario():
        plain_id, _ = await router_async_task.start_task("example", "plain")
        detailed_id, _ = await router_async_task.start_task("example", "detailed")
        await router_async_task.complete_task(plain_id, "example", result)
        await router_async_task.complete_task(
            detailed_id,
            "example",
            result,
            status_code=201,
            message="created",
        )
        return (
            await router_async_task.load_task(plain_id, "example"),
            await router_async_task.load_task(detailed_id, "example"),
        )

    plain_entry, detailed_entry = asyncio.run(run_scenario())

    assert plain_entry.state == schemas_async_task.TASK_STATE_COMPLETED
    assert plain_entry.status is None
    assert plain_entry.message is None
    assert plain_entry.result == {
        "status": 200,
        "message": "ok",
        "data": "done",
        "extra": None,
    }
    assert detailed_entry.status == 201
    assert detailed_entry.message == "created"
    assert detailed_entry.result == plain_entry.result


def test_complete_task_resets_the_configured_lifetime(controllable_task_cache):
    result = base_req_resp.BaseResponse[str](status=200, message="ok", data="done")

    async def run_scenario():
        task_id, _ = await router_async_task.start_task("example", "expiring-completion")
        controllable_task_cache.advance(_BEFORE_EXPIRY_SECONDS)
        await router_async_task.complete_task(task_id, "example", result)
        immediate = await router_async_task.load_task(task_id, "example")
        controllable_task_cache.advance(_PAST_EXPIRY_SECONDS)
        after_original_expiry = await router_async_task.load_task(task_id, "example")
        controllable_task_cache.advance(_PAST_RESET_EXPIRY_SECONDS)
        with pytest.raises(HTTPException) as exc_info:
            await router_async_task.load_task(task_id, "example")
        return immediate, after_original_expiry, exc_info.value.status_code

    immediate, after_original_expiry, expired_status = asyncio.run(run_scenario())

    assert immediate.state == schemas_async_task.TASK_STATE_COMPLETED
    assert after_original_expiry.state == schemas_async_task.TASK_STATE_COMPLETED
    assert expired_status == 404


def test_fail_task_round_trips_optional_result_and_defaults():
    result = base_req_resp.BaseResponse[str](status=502, message="failed", data="baseline")

    async def run_scenario():
        default_id, _ = await router_async_task.start_task("example", "default")
        detailed_id, _ = await router_async_task.start_task("example", "detailed")
        await router_async_task.fail_task(default_id, "example")
        await router_async_task.fail_task(
            detailed_id,
            "example",
            status_code=502,
            message="analysis failed",
            result=result,
        )
        return (
            await router_async_task.load_task(default_id, "example"),
            await router_async_task.load_task(detailed_id, "example"),
        )

    default_entry, detailed_entry = asyncio.run(run_scenario())

    assert default_entry.state == schemas_async_task.TASK_STATE_FAILED
    assert default_entry.status is None
    assert default_entry.message == "Task failed"
    assert default_entry.result is None
    assert detailed_entry.status == 502
    assert detailed_entry.message == "analysis failed"
    assert detailed_entry.result == {
        "status": 502,
        "message": "failed",
        "data": "baseline",
        "extra": None,
    }


def test_fail_task_resets_the_configured_lifetime(controllable_task_cache):
    async def run_scenario():
        task_id, _ = await router_async_task.start_task("example", "expiring-failure")
        controllable_task_cache.advance(_BEFORE_EXPIRY_SECONDS)
        await router_async_task.fail_task(task_id, "example", status_code=502)
        immediate = await router_async_task.load_task(task_id, "example")
        controllable_task_cache.advance(_PAST_EXPIRY_SECONDS)
        after_original_expiry = await router_async_task.load_task(task_id, "example")
        controllable_task_cache.advance(_PAST_RESET_EXPIRY_SECONDS)
        with pytest.raises(HTTPException) as exc_info:
            await router_async_task.load_task(task_id, "example")
        return immediate, after_original_expiry, exc_info.value.status_code

    immediate, after_original_expiry, expired_status = asyncio.run(run_scenario())

    assert immediate.state == schemas_async_task.TASK_STATE_FAILED
    assert after_original_expiry.state == schemas_async_task.TASK_STATE_FAILED
    assert expired_status == 404


@pytest.mark.parametrize(
    ("cached_entry", "expected_status"),
    [
        (None, 404),
        ("not-an-entry", 404),
        ({"task_type": "other", "state": schemas_async_task.TASK_STATE_RUNNING}, 404),
        ({"task_type": "example", "state": "UNKNOWN"}, 500),
        ({"task_type": "example", "state": schemas_async_task.TASK_STATE_COMPLETED}, 500),
        (
            {
                "task_type": "example",
                "state": schemas_async_task.TASK_STATE_RUNNING,
                "message": "unexpected",
            },
            500,
        ),
        (
            {
                "task_type": "example",
                "state": schemas_async_task.TASK_STATE_FAILED,
                "unexpected": True,
            },
            500,
        ),
    ],
)
def test_load_task_rejects_missing_wrong_type_or_malformed_entries(cached_entry, expected_status):
    with (
        mock.patch.object(
            router_async_task.cache,
            "get",
            new_callable=mock.AsyncMock,
            return_value=cached_entry,
        ),
        pytest.raises(HTTPException) as exc_info,
    ):
        asyncio.run(router_async_task.load_task("unknown-task", "example"))

    assert exc_info.value.status_code == expected_status


@pytest.mark.parametrize(
    "cached_entry",
    [
        "not-an-entry",
        {"task_type": "other", "state": schemas_async_task.TASK_STATE_RUNNING},
        {"task_type": "example", "state": "UNKNOWN"},
    ],
)
def test_start_task_rejects_invalid_existing_entries(cached_entry):
    with (
        mock.patch.object(
            router_async_task.cache,
            "get",
            new_callable=mock.AsyncMock,
            return_value=cached_entry,
        ),
        pytest.raises(HTTPException) as exc_info,
    ):
        asyncio.run(router_async_task.start_task("example", "input"))

    assert exc_info.value.status_code == 500


@pytest.mark.parametrize(
    ("stored_status", "expected_status"),
    [
        (None, 500),
        (399, 500),
        (400, 400),
        (599, 599),
        (600, 500),
    ],
)
def test_failure_status_accepts_only_http_error_boundaries(stored_status, expected_status):
    async def run_scenario():
        task_id, _ = await router_async_task.start_task("example", str(stored_status))
        await router_async_task.fail_task(task_id, "example", status_code=stored_status)
        return await router_async_task.load_task(task_id, "example")

    task_entry = asyncio.run(run_scenario())

    assert router_async_task.failure_status(task_entry) == expected_status
