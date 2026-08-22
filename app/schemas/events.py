from ..models import event as models_event
from . import async_task
from .base_req_resp import BaseResponse


class UpcomingEarningsResponse(BaseResponse[list[models_event.UpcomingEarningsEvent]]):
    """Response envelope containing upcoming earnings events."""


class UpcomingDividendsResponse(BaseResponse[list[models_event.UpcomingDividendEvent]]):
    """Response envelope containing upcoming dividend events."""


class UpcomingDividendsAsyncResponse(async_task.AsyncTaskResponse[list[models_event.UpcomingDividendEvent]]):
    """Background-task response for upcoming dividend events."""


class UpcomingEarningsAsyncResponse(async_task.AsyncTaskResponse[list[models_event.UpcomingEarningsEvent]]):
    """Background-task response for upcoming earnings events."""
