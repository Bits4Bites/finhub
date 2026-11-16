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


class TaskEntry(BaseModel):
    """Validated lifecycle snapshot returned by ``load_task``.

    Attributes:
        task_type: Workflow category that owns the task.
        state: Current running, completed, or failed lifecycle state.
        status: Optional application or HTTP status recorded by a terminal task.
        message: Optional caller-facing terminal summary.
        result: Optional JSON-compatible terminal response data.

    Notes:
        Running entries cannot contain terminal fields, and completed entries
        always contain a result. Failed entries may preserve partial result data.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    task_type: str = Field(min_length=1, description="Workflow category that owns the task.")
    state: schemas_async_task.TaskState = Field(description="Current task lifecycle state.")
    status: int | None = Field(default=None, description="Optional status recorded by a terminal task.")
    message: str | None = Field(default=None, description="Optional caller-facing terminal summary.")
    result: dict[str, Any] | None = Field(
        default=None,
        description="Optional JSON-compatible terminal response data.",
    )

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


async def _store(task_id: str, entry: TaskEntry) -> None:
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
    """Create a running task entry or reuse the matching persisted task.

    Args:
        task_type: Non-empty task category used to keep unrelated workflows separate.
        task_input: Ordered string or Pydantic-model values that identify the request.
            Models are identified by their JSON representation.

    Returns:
        The task identifier and ``True`` when a new running task was persisted.
        ``False`` means an existing running, completed, or failed task was reused.

    Raises:
        HTTPException: With status 500 when a matching stored entry has the wrong
            task type or is malformed.
        ValidationError: If a new task entry does not satisfy the persistence contract.
        Exception: Cache-backend failures propagate.

    Notes:
        Equivalent inputs are deduplicated atomically within this process. Task
        identifiers and entries are process-local, and entries expire after the
        configured asynchronous-task lifetime.
    """
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
                TaskEntry.model_validate(cached_entry)
            except ValidationError as exc:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Invalid task state",
                ) from exc
            return task_id, False

        await _store(
            task_id,
            TaskEntry(
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
    """Persist a successful terminal result for later polling.

    Args:
        task_id: Identifier returned by ``start_task``.
        task_type: Task category that pollers must supply when loading the result.
        result: Pydantic response model to serialize into JSON-compatible data.
        status_code: Optional application or HTTP status associated with the result.
        message: Optional caller-facing completion summary.

    Returns:
        None.

    Raises:
        ValidationError: If the completed entry violates the task persistence contract.
        Exception: Result-serialization and cache-backend failures propagate.

    Notes:
        The completed entry replaces any value already stored under ``task_id`` and
        starts a fresh configured asynchronous-task lifetime.
    """
    await _store(
        task_id,
        TaskEntry(
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
    """Persist a failed terminal task for later polling.

    Args:
        task_id: Identifier returned by ``start_task``.
        task_type: Task category that pollers must supply when loading the failure.
        status_code: Optional application or HTTP failure status.
        message: Caller-facing failure summary; defaults to ``"Task failed"``.
        result: Optional structured response to preserve partial or baseline data.

    Returns:
        None.

    Raises:
        ValidationError: If the failed entry violates the task persistence contract.
        Exception: Result-serialization and cache-backend failures propagate.

    Notes:
        The result is serialized into JSON-compatible data when supplied. The failed
        entry replaces any value already stored under ``task_id`` and starts a fresh
        configured asynchronous-task lifetime.
    """
    await _store(
        task_id,
        TaskEntry(
            task_type=task_type,
            state=schemas_async_task.TASK_STATE_FAILED,
            status=status_code,
            message=message,
            result=_serialize_result(result),
        ),
    )


async def load_task(task_id: str, task_type: str) -> TaskEntry:
    """Load and validate a persisted task for a specific workflow.

    Args:
        task_id: Identifier returned by ``start_task``.
        task_type: Expected task category.

    Returns:
        A validated task entry containing its lifecycle state and any optional
        status, message, or serialized result.

    Raises:
        HTTPException: With status 404 when the identifier is missing, expired, or
            belongs to another task type, or status 500 when a matching entry is
            malformed.
        Exception: Cache-backend failures propagate.
    """
    task_entry = await cache.get(task_id)
    if not isinstance(task_entry, dict) or task_entry.get("task_type") != task_type:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    try:
        return TaskEntry.model_validate(task_entry)
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Invalid task state") from exc


def failure_status(task_entry: TaskEntry) -> int:
    """Choose the public HTTP status for a failed task.

    Args:
        task_entry: Validated failed task entry returned by ``load_task``.

    Returns:
        The stored status when it is between 400 and 599 inclusive; otherwise
        HTTP 500.
    """
    if task_entry.status is not None and 400 <= task_entry.status <= 599:
        return task_entry.status
    return status.HTTP_500_INTERNAL_SERVER_ERROR
