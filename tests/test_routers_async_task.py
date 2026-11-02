import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.routers import async_task as router_async_task
from app.schemas import async_task as schemas_async_task
from app.schemas import base_req_resp


def test_start_task_stores_shared_running_entry():
    with (
        patch.object(router_async_task, "_generate_task_id", return_value="task-123"),
        patch.object(router_async_task.cache, "set", new_callable=AsyncMock, return_value=True) as mock_set,
    ):
        task_id, is_new = asyncio.run(router_async_task.start_task("example", "input"))

    assert task_id == "task-123"
    assert is_new is True
    mock_set.assert_awaited_once_with(
        "task-123",
        {
            "task_type": "example",
            "state": schemas_async_task.TASK_STATE_RUNNING,
        },
        ttl=schemas_async_task.ASYNC_TASK_TTL,
    )


def test_start_task_deduplicates_concurrent_identical_inputs():
    entries = {}

    async def get_entry(task_id):
        await asyncio.sleep(0)
        return entries.get(task_id)

    async def set_entry(task_id, entry, ttl):
        entries[task_id] = entry
        return True

    async def start_twice():
        return await asyncio.gather(
            router_async_task.start_task("example", "same-input"),
            router_async_task.start_task("example", "same-input"),
        )

    with (
        patch.object(router_async_task, "_generate_task_id", return_value="task-123"),
        patch.object(router_async_task.cache, "get", side_effect=get_entry),
        patch.object(router_async_task.cache, "set", side_effect=set_entry) as mock_set,
    ):
        results = asyncio.run(start_twice())

    assert results == [("task-123", True), ("task-123", False)]
    mock_set.assert_awaited_once()


def test_generate_task_id_is_process_local_and_input_dependent():
    first_id = router_async_task._generate_task_id("example", "input")

    assert router_async_task._generate_task_id("example", "input") == first_id
    assert router_async_task._generate_task_id("example", "other-input") != first_id
    assert router_async_task._generate_task_id("other-task", "input") != first_id


def test_complete_task_serializes_response():
    result = base_req_resp.BaseResponse[str](status=200, message="ok", data="done")
    with patch.object(router_async_task.cache, "set", new_callable=AsyncMock, return_value=True) as mock_set:
        asyncio.run(router_async_task.complete_task("task-123", "example", result))

    assert mock_set.await_args.args[1] == {
        "task_type": "example",
        "state": schemas_async_task.TASK_STATE_COMPLETED,
        "result": {
            "status": 200,
            "message": "ok",
            "data": "done",
            "extra": None,
        },
    }


def test_fail_task_preserves_status_message_and_result():
    result = base_req_resp.BaseResponse[str](status=502, message="failed", data="baseline")
    with patch.object(router_async_task.cache, "set", new_callable=AsyncMock, return_value=True) as mock_set:
        asyncio.run(
            router_async_task.fail_task(
                "task-123",
                "example",
                status_code=502,
                message="failed",
                result=result,
            )
        )

    cached_entry = mock_set.await_args.args[1]
    assert cached_entry["state"] == schemas_async_task.TASK_STATE_FAILED
    assert cached_entry["status"] == 502
    assert cached_entry["message"] == "failed"
    assert cached_entry["result"]["data"] == "baseline"


def test_load_task_validates_task_type_and_state():
    with patch.object(
        router_async_task.cache,
        "get",
        new_callable=AsyncMock,
        return_value={
            "task_type": "example",
            "state": schemas_async_task.TASK_STATE_COMPLETED,
            "result": {"status": 200, "message": "ok"},
        },
    ):
        task_entry = asyncio.run(router_async_task.load_task("task-123", "example"))

    assert task_entry.state == schemas_async_task.TASK_STATE_COMPLETED
    assert task_entry.result == {"status": 200, "message": "ok"}


@pytest.mark.parametrize(
    ("cached_entry", "expected_status"),
    [
        (None, 404),
        ({"task_type": "other", "state": schemas_async_task.TASK_STATE_RUNNING}, 404),
        ({"task_type": "example", "state": "UNKNOWN"}, 500),
        ({"task_type": "example", "state": schemas_async_task.TASK_STATE_COMPLETED}, 500),
    ],
)
def test_load_task_rejects_missing_or_invalid_entries(cached_entry, expected_status):
    with (
        patch.object(
            router_async_task.cache,
            "get",
            new_callable=AsyncMock,
            return_value=cached_entry,
        ),
        pytest.raises(HTTPException) as exc_info,
    ):
        asyncio.run(router_async_task.load_task("task-123", "example"))

    assert exc_info.value.status_code == expected_status
