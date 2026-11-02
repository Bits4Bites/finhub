from __future__ import annotations

import asyncio
import hmac
import secrets
from typing import Any, Self

from fastapi import HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from ..schemas import async_task as schemas_async_task
from ..utils import cache

_TASK_ID_SECRET = secrets.token_bytes(32)
_TASK_START_LOCK = asyncio.Lock()


class _TaskEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    task_type: str = Field(min_length=1)
    state: schemas_async_task.TaskState
    status: int | None = None
    message: str | None = None
    result: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_state(self) -> Self:
        if self.state == schemas_async_task.TASK_STATE_RUNNING:
            if self.status is not None or self.message is not None or self.result is not None:
                raise ValueError("running task cannot contain a result")
        elif self.state == schemas_async_task.TASK_STATE_COMPLETED and self.result is None:
            raise ValueError("completed task requires a result")
        return self


def _serialize_result(result: BaseModel | None) -> dict[str, Any] | None:
    return result.model_dump(mode="json") if result is not None else None


async def _store(task_id: str, entry: _TaskEntry) -> None:
    await cache.set(
        task_id,
        entry.model_dump(mode="json", exclude_none=True),
        ttl=schemas_async_task.ASYNC_TASK_TTL,
    )


def _generate_task_id(task_type: str, *task_input: str | BaseModel) -> str:
    normalized_input = tuple(item.model_dump_json() if isinstance(item, BaseModel) else item for item in task_input)
    request_key = cache.generate_key("async-task", task_type, *normalized_input)
    return hmac.new(_TASK_ID_SECRET, request_key.encode(), digestmod="sha256").hexdigest()


async def start_task(task_type: str, *task_input: str | BaseModel) -> tuple[str, bool]:
    task_id = _generate_task_id(task_type, *task_input)
    async with _TASK_START_LOCK:
        cached_entry = await cache.get(task_id)
        if cached_entry is not None:
            if not isinstance(cached_entry, dict) or cached_entry.get("task_type") != task_type:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Invalid task state",
                )
            try:
                _TaskEntry.model_validate(cached_entry)
            except ValidationError as exc:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Invalid task state",
                ) from exc
            return task_id, False

        await _store(
            task_id,
            _TaskEntry(
                task_type=task_type,
                state=schemas_async_task.TASK_STATE_RUNNING,
            ),
        )
        return task_id, True


async def complete_task(
    task_id: str,
    task_type: str,
    result: BaseModel,
    *,
    status_code: int | None = None,
    message: str | None = None,
) -> None:
    await _store(
        task_id,
        _TaskEntry(
            task_type=task_type,
            state=schemas_async_task.TASK_STATE_COMPLETED,
            status=status_code,
            message=message,
            result=_serialize_result(result),
        ),
    )


async def fail_task(
    task_id: str,
    task_type: str,
    *,
    status_code: int | None = None,
    message: str = "Task failed",
    result: BaseModel | None = None,
) -> None:
    await _store(
        task_id,
        _TaskEntry(
            task_type=task_type,
            state=schemas_async_task.TASK_STATE_FAILED,
            status=status_code,
            message=message,
            result=_serialize_result(result),
        ),
    )


async def load_task(task_id: str, task_type: str) -> _TaskEntry:
    task_entry = await cache.get(task_id)
    if not isinstance(task_entry, dict) or task_entry.get("task_type") != task_type:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    try:
        return _TaskEntry.model_validate(task_entry)
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Invalid task state") from exc


def failure_status(task_entry: _TaskEntry) -> int:
    if task_entry.status is not None and 400 <= task_entry.status <= 599:
        return task_entry.status
    return status.HTTP_500_INTERNAL_SERVER_ERROR
