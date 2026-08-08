from pydantic import BaseModel

from ..models import event as models_event
from . import async_task
from .base_req_resp import BaseResponse


class UpcomingEarningsResponse(BaseResponse):
    data: list[models_event.UpcomingEarningsEvent] | None = None


class UpcomingDividendsResponse(BaseResponse):
    data: list[models_event.UpcomingDividendEvent] | None = None


class AsyncTaskInfo(BaseModel):
    task_id: str
    state: async_task.TaskState | None = None


class UpcomingDividendsAsyncResponse(UpcomingDividendsResponse):
    extra: AsyncTaskInfo


class ListingsResponse(BaseResponse):
    data: list[models_event.ListingEvent] | None = None
