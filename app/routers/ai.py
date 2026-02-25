from fastapi import APIRouter, Query

from ..schemas import finhub as schemas
from ..services import ai as ai_service

router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/event/earnings", response_model=schemas.IncomingEarningsResponse, response_model_exclude_none=True)
async def get_incoming_earnings_event(
    country: str = Query("", description="Country code to filter events by (e.g., 'AU', 'US', 'VN', etc.)."),
    index: str = Query(
        "", description="Optional stock index to filter events by (e.g., 'NASDAQ 100', 'S&P/ASX 200', etc.)."
    ),
) -> schemas.IncomingEarningsResponse:
    """
    Check for incoming earnings events for a market, using AI assistance.
    """
    events = await ai_service.ai_get_incoming_earnings_events(country, index)
    return schemas.IncomingEarningsResponse(status=200, message="ok", data=events)


@router.get("/event/dividends", response_model=schemas.IncomingDividendsResponse, response_model_exclude_none=True)
async def get_incoming_dividends_event(
    country: str = Query("", description="Country code to filter events by (e.g., 'AU', 'US', 'VN', etc.)."),
    index: str = Query(
        "", description="Optional stock index to filter events by (e.g., 'NASDAQ 100', 'S&P/ASX 200', etc.)."
    ),
) -> schemas.IncomingDividendsResponse:
    """
    Check for incoming dividend/distribution events for a market, using AI assistance.
    """
    events = await ai_service.ai_get_incoming_dividends_events(country, index)
    return schemas.IncomingDividendsResponse(status=200, message="ok", data=events)
