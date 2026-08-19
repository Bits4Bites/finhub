from ..models import events_listings as models_events_listings
from . import events as schemas_events
from .base_req_resp import BaseResponse


class ListingsResponse(BaseResponse):
    data: list[models_events_listings.ListingEvent] | None = None


class ListingsAsyncResponse(ListingsResponse):
    extra: schemas_events.AsyncTaskInfo
