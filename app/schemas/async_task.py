from typing import Generic, Literal

from pydantic import BaseModel, Field

from .base_req_resp import BaseResponse, ResponseDataT

ASYNC_TASK_TTL = 60 * 60

TaskState = Literal["RUNNING", "COMPLETED", "FAILED"]
TASK_STATE_RUNNING: TaskState = "RUNNING"
TASK_STATE_COMPLETED: TaskState = "COMPLETED"
TASK_STATE_FAILED: TaskState = "FAILED"


class AsyncTaskInfo(BaseModel):
    """Identity and lifecycle state of a background API task."""

    task_id: str = Field(description="Identifier used to poll the background task.")
    state: TaskState | None = Field(
        default=None,
        description="Current lifecycle state of the background task.",
    )


class AsyncTaskResponse(BaseResponse[ResponseDataT], Generic[ResponseDataT]):  # noqa: UP046
    """Generic response envelope for background-task start and poll operations."""

    extra: AsyncTaskInfo = Field(description="Background-task identity and current state.")
