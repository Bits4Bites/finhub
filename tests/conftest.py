import uuid

import pytest
from fastapi import HTTPException, status
from pydantic import BaseModel

from app import config
from app.routers import async_task as router_async_task
from app.schemas import async_task as schemas_async_task


@pytest.fixture(autouse=True)
def disable_api_auth(monkeypatch):
    monkeypatch.setattr(config.settings_app, "api_key", "")


class _ManualClock:
    def __init__(self) -> None:
        self._now = 0.0

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


class _DeferredTaskStore:
    """Deterministic task repository fake driven only through its public API."""

    def __init__(self, *, ttl_seconds: float = 10.0) -> None:
        self._clock = _ManualClock()
        self._ttl_seconds = ttl_seconds
        self._entries: dict[str, tuple[router_async_task.TaskEntry, float]] = {}
        self._identities: dict[tuple[str, ...], str] = {}
        self._pending: list[tuple[str, router_async_task.TaskEntry]] = []

    @staticmethod
    def _identity(task_type: str, task_input: tuple[str | BaseModel, ...]) -> tuple[str, ...]:
        normalized = tuple(item.model_dump_json() if isinstance(item, BaseModel) else item for item in task_input)
        return (task_type, *normalized)

    def _put(self, task_id: str, entry: router_async_task.TaskEntry) -> None:
        self._entries[task_id] = (entry, self._clock() + self._ttl_seconds)

    def _get(self, task_id: str) -> router_async_task.TaskEntry | None:
        stored = self._entries.get(task_id)
        if stored is None:
            return None
        entry, expires_at = stored
        if self._clock() >= expires_at:
            self._entries.pop(task_id, None)
            return None
        return entry.model_copy(deep=True)

    async def start(self, task_type: str, *task_input: str | BaseModel) -> tuple[str, bool]:
        identity = self._identity(task_type, task_input)
        task_id = self._identities.setdefault(identity, uuid.uuid4().hex)
        if self._get(task_id) is not None:
            return task_id, False
        self._put(
            task_id,
            router_async_task.TaskEntry(
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
        self._pending.append(
            (
                task_id,
                router_async_task.TaskEntry(
                    task_type=task_type,
                    state=schemas_async_task.TASK_STATE_COMPLETED,
                    status=status_code,
                    message=message,
                    result=result.model_dump(mode="json"),
                ),
            )
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
        self._pending.append(
            (
                task_id,
                router_async_task.TaskEntry(
                    task_type=task_type,
                    state=schemas_async_task.TASK_STATE_FAILED,
                    status=status_code,
                    message=message,
                    result=result.model_dump(mode="json") if result is not None else None,
                ),
            )
        )

    async def load(self, task_id: str, task_type: str) -> router_async_task.TaskEntry:
        entry = self._get(task_id)
        if entry is None or entry.task_type != task_type:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        return entry

    def release(self) -> None:
        pending, self._pending = self._pending, []
        for task_id, entry in pending:
            self._put(task_id, entry)

    def advance(self, seconds: float) -> None:
        self._clock.advance(seconds)


@pytest.fixture
def deferred_task_store(monkeypatch):
    task_store = _DeferredTaskStore()
    monkeypatch.setattr(router_async_task, "task_store", task_store)
    return task_store
