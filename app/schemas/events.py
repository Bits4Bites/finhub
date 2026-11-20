from ..models import events_div as models_dividends
from ..models import events_earnings as models_earnings
from . import async_task
from .base_req_resp import BaseResponse


class UpcomingEarningsResponse(BaseResponse[list[models_earnings.UpcomingEarningsEvent]]):
    """Response envelope containing upcoming earnings events."""


class UpcomingDividendsResponse(BaseResponse[list[models_dividends.UpcomingDividendEvent]]):
    """Response envelope containing upcoming dividend events."""


class UpcomingDividendsAsyncResponse(async_task.AsyncTaskResponse[list[models_dividends.UpcomingDividendEvent]]):
    """Background-task response for upcoming dividend events."""


class UpcomingEarningsAsyncResponse(async_task.AsyncTaskResponse[list[models_earnings.UpcomingEarningsEvent]]):
    """Background-task response for upcoming earnings events."""
