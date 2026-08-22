from ..models import event as models_event
from . import async_task
from .base_req_resp import BaseResponse


class UpcomingEarningsResponse(BaseResponse[list[models_event.UpcomingEarningsEvent]]):
    pass


class UpcomingDividendsResponse(BaseResponse[list[models_event.UpcomingDividendEvent]]):
    pass


class UpcomingDividendsAsyncResponse(async_task.AsyncTaskResponse[list[models_event.UpcomingDividendEvent]]):
    pass


class UpcomingEarningsAsyncResponse(async_task.AsyncTaskResponse[list[models_event.UpcomingEarningsEvent]]):
    pass
