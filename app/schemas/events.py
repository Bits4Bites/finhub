from ..models import event as models_event
from .base_req_resp import BaseResponse


class UpcomingEarningsResponse(BaseResponse):
    data: list[models_event.UpcomingEarningsEvent] | None = None


class UpcomingDividendsResponse(BaseResponse):
    data: list[models_event.UpcomingDividendEvent] | None = None


class ListingsResponse(BaseResponse):
    data: list[models_event.ListingEvent] | None = None
