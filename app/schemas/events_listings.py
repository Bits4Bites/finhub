from ..models import events_listings as models_events_listings
from . import async_task
from .base_req_resp import BaseResponse


class ListingsResponse(BaseResponse[list[models_events_listings.ListingEvent]]):
    """Response envelope containing new-listing events."""


class ListingsAsyncResponse(async_task.AsyncTaskResponse[list[models_events_listings.ListingEvent]]):
    """Background-task response for new-listing events."""
