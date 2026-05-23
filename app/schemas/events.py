from ..models import finhub as models
from .base_req_resp import BaseResponse


class UpcomingEarningsResponse(BaseResponse):
    data: list[models.UpcomingEarningsEvent] | None = None


class UpcomingDividendsResponse(BaseResponse):
    data: list[models.UpcomingDividendEvent] | None = None


class ListingsResponse(BaseResponse):
    data: list[models.ListingEvent] | None = None
