from __future__ import annotations

import asyncio
import hmac
import secrets
from typing import Any, Protocol, Self

from fastapi import HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from ..schemas import async_task as schemas_async_task
from ..utils import cache


def validation_error_response(
    description: str,
    *application_models: type[BaseModel],
) -> dict[str, Any]:
    """Describe request validation and application-level errors for OpenAPI.

    Args:
        description: Caller-facing explanation of the invalid request.
        application_models: Additional response-envelope models that the
            operation can return with HTTP 422 after request validation.

    Returns:
        A FastAPI ``responses`` entry accepting the standard validation-error
        body and each supplied application response model.
    """
    schemas = [{"$ref": "#/components/schemas/HTTPValidationError"}]
    schemas.extend({"$ref": f"#/components/schemas/{model.__name__}"} for model in application_models)
    return {
        "description": description,
        "content": {
            "application/json": {
                "schema": {"anyOf": schemas},
            }
        },
    }


class TaskEntry(BaseModel):
    """Validated lifecycle snapshot returned by a task store.

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
    def _validate_state(self) -> Self:
        if self.state == schemas_async_task.TASK_STATE_RUNNING:
            if self.status is not None or self.message is not None or self.result is not None:
                raise ValueError("running task cannot contain a result")
        elif self.state == schemas_async_task.TASK_STATE_COMPLETED and self.result is None:
            raise ValueError("completed task requires a result")
        return self

    @property
    def failure_http_status(self) -> int:
        """Return the public HTTP status for this failed task.

        Returns:
            The stored status when it is between 400 and 599 inclusive;
            otherwise HTTP 500.
        """
        if self.status is not None and 400 <= self.status <= 599:
            return self.status
        return status.HTTP_500_INTERNAL_SERVER_ERROR


class TaskStore(Protocol):
    """Persistence boundary used by asynchronous start and poll endpoints."""

    async def start(self, task_type: str, *task_input: str | BaseModel) -> tuple[str, bool]:
        """Create or reuse a task identified by workflow and normalized input.

        Args:
            task_type: Non-empty workflow category.
            task_input: Ordered strings or Pydantic request models identifying
                an equivalent start request.

        Returns:
            The opaque task identifier and whether a new running entry was
            created.
        """
        ...

    async def complete(
        self,
        task_id: str,
        task_type: str,
        result: BaseModel,
        *,
        status_code: int | None = None,
        message: str | None = None,
    ) -> None:
        """Persist a successful terminal result.

        Args:
            task_id: Identifier returned by ``start``.
            task_type: Workflow category that owns the task.
            result: Response model to retain for polling.
            status_code: Optional application or HTTP completion status.
            message: Optional caller-facing completion summary.
        """
        ...

    async def fail(
        self,
        task_id: str,
        task_type: str,
        *,
        status_code: int | None = None,
        message: str = "Task failed",
        result: BaseModel | None = None,
    ) -> None:
        """Persist a failed terminal result.

        Args:
            task_id: Identifier returned by ``start``.
            task_type: Workflow category that owns the task.
            status_code: Optional application or HTTP failure status.
            message: Caller-facing failure summary.
            result: Optional response model preserving partial result data.
        """
        ...

    async def load(self, task_id: str, task_type: str) -> TaskEntry:
        """Load a task for its owning workflow.

        Args:
            task_id: Identifier returned by ``start``.
            task_type: Expected workflow category.

        Returns:
            The validated retained lifecycle snapshot.
        """
        ...


class CacheTaskStore:
    """Process-local task store backed by the application cache.

    Equivalent requests reuse one opaque task identifier while the retained
    running or terminal entry remains unexpired. Every lifecycle write starts a
    fresh configured task lifetime.
    """

    def __init__(self) -> None:
        self._id_secret = secrets.token_bytes(32)
        self._start_lock = asyncio.Lock()

    @staticmethod
    def _serialize_result(result: BaseModel | None) -> dict[str, Any] | None:
        return result.model_dump(mode="json") if result is not None else None

    def _generate_id(self, task_type: str, *task_input: str | BaseModel) -> str:
        normalized_input = tuple(item.model_dump_json() if isinstance(item, BaseModel) else item for item in task_input)
        request_key = cache.generate_key("async-task", task_type, *normalized_input)
        return hmac.new(self._id_secret, request_key.encode(), digestmod="sha256").hexdigest()

    @staticmethod
    async def _store(task_id: str, entry: TaskEntry) -> None:
        await cache.set(
            task_id,
            entry.model_dump(mode="json", exclude_none=True),
            ttl=schemas_async_task.ASYNC_TASK_TTL,
        )

    async def start(self, task_type: str, *task_input: str | BaseModel) -> tuple[str, bool]:
        """Create a running task or reuse its retained lifecycle state.

        Args:
            task_type: Non-empty workflow category.
            task_input: Ordered strings or Pydantic request models identifying
                an equivalent start request.

        Returns:
            The opaque task identifier and whether a new running entry was
            created.

        Raises:
            HTTPException: HTTP 500 when a matching retained entry is invalid.
            Exception: Cache failures propagate.
        """
        task_id = self._generate_id(task_type, *task_input)
        async with self._start_lock:
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

            await self._store(
                task_id,
                TaskEntry(
                    task_type=task_type,
                    state=schemas_async_task.TASK_STATE_RUNNING,
                ),
            )
            return task_id, True

    async def complete(
        self,
        task_id: str,
        task_type: str,
        result: BaseModel,
        *,
        status_code: int | None = None,
        message: str | None = None,
    ) -> None:
        """Persist a completed result and restart its retention lifetime.

        Args:
            task_id: Identifier returned by ``start``.
            task_type: Workflow category that owns the task.
            result: Response model serialized into JSON-compatible data.
            status_code: Optional application or HTTP completion status.
            message: Optional caller-facing completion summary.

        Raises:
            ValidationError: If the completed entry violates the lifecycle contract.
            Exception: Serialization and cache failures propagate.
        """
        await self._store(
            task_id,
            TaskEntry(
                task_type=task_type,
                state=schemas_async_task.TASK_STATE_COMPLETED,
                status=status_code,
                message=message,
                result=self._serialize_result(result),
            ),
        )

    async def fail(
        self,
        task_id: str,
        task_type: str,
        *,
        status_code: int | None = None,
        message: str = "Task failed",
        result: BaseModel | None = None,
    ) -> None:
        """Persist a failed result and restart its retention lifetime.

        Args:
            task_id: Identifier returned by ``start``.
            task_type: Workflow category that owns the task.
            status_code: Optional application or HTTP failure status.
            message: Caller-facing failure summary.
            result: Optional response model preserving partial result data.

        Raises:
            ValidationError: If the failed entry violates the lifecycle contract.
            Exception: Serialization and cache failures propagate.
        """
        await self._store(
            task_id,
            TaskEntry(
                task_type=task_type,
                state=schemas_async_task.TASK_STATE_FAILED,
                status=status_code,
                message=message,
                result=self._serialize_result(result),
            ),
        )

    async def load(self, task_id: str, task_type: str) -> TaskEntry:
        """Load a retained task owned by the requested workflow.

        Args:
            task_id: Identifier returned by ``start``.
            task_type: Expected workflow category.

        Returns:
            The validated lifecycle snapshot.

        Raises:
            HTTPException: HTTP 404 when the task is missing, expired, or owned
                by another workflow; HTTP 500 when retained state is invalid.
            Exception: Cache failures propagate.
        """
        task_entry = await cache.get(task_id)
        if not isinstance(task_entry, dict) or task_entry.get("task_type") != task_type:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        try:
            return TaskEntry.model_validate(task_entry)
        except ValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Invalid task state",
            ) from exc


task_store: TaskStore = CacheTaskStore()
