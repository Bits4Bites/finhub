from typing import Generic, Literal

from pydantic import BaseModel

from .base_req_resp import BaseResponse, ResponseDataT

ASYNC_TASK_TTL = 60 * 60

TaskState = Literal["RUNNING", "COMPLETED", "FAILED"]
TASK_STATE_RUNNING: TaskState = "RUNNING"
TASK_STATE_COMPLETED: TaskState = "COMPLETED"
TASK_STATE_FAILED: TaskState = "FAILED"


class AsyncTaskInfo(BaseModel):
    task_id: str
    state: TaskState | None = None


class AsyncTaskResponse(BaseResponse[ResponseDataT], Generic[ResponseDataT]):  # noqa: UP046
    extra: AsyncTaskInfo
