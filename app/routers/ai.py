from fastapi import APIRouter, Query

from ..schemas import finhub as schemas
from ..services import ai as ai_service

router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/event/earnings", response_model=schemas.UpcomingEarningsResponse, response_model_exclude_none=True)
async def get_incoming_earnings_event(
    country: str = Query("", description="Country code to filter events by (e.g., 'AU', 'US', 'VN', etc.)."),
    index: str = Query(
        "", description="Optional stock index to filter events by (e.g., 'NASDAQ 100', 'S&P/ASX 200', etc.)."
    ),
) -> schemas.UpcomingEarningsResponse:
    """
    Check for upcoming earnings events for a market, using AI assistance.
    """
    country = country.upper()
    match country:
        case "AU" | "AUS" | "AUSTRALIA":
            events = await ai_service.ai_get_asx_upcoming_earnings_events(index)
        case "US" | "USA" | "UNITED STATES":
            events = await ai_service.ai_get_us_upcoming_earnings_events(index)
        case _:
            return schemas.UpcomingEarningsResponse(status=501, message=f"Unsupported country '{country}'")
            # events = await ai_service.ai_get_incoming_earnings_events(country, index)

    return schemas.UpcomingEarningsResponse(status=200, message="ok", data=events)


@router.get("/event/dividends", response_model=schemas.UpcomingDividendsResponse, response_model_exclude_none=True)
async def get_upcoming_dividends_event(
    country: str = Query("", description="Country code to filter events by (e.g., 'AU', 'US', 'VN', etc.)."),
    index: str = Query(
        "", description="Optional stock index to filter events by (e.g., 'NASDAQ 100', 'S&P/ASX 200', etc.)."
    ),
) -> schemas.UpcomingDividendsResponse:
    """
    Check for upcoming dividend/distribution events for a market, using AI assistance.
    """
    country = country.upper()
    match country:
        case "AU" | "AUS" | "AUSTRALIA":
            events = await ai_service.ai_get_asx_upcoming_dividends_events(index)
        case "US" | "USA" | "UNITED STATES":
            events = await ai_service.ai_get_us_upcoming_dividends_events(index)
        case "VN" | "VIETNAM":
            events = await ai_service.ai_get_vn_upcoming_dividends_events(index)
        case _:
            return schemas.UpcomingDividendsResponse(status=501, message=f"Unsupported country '{country}'")
            # events = await ai_service.ai_get_incoming_dividends_events(country, index)

    return schemas.UpcomingDividendsResponse(status=200, message="ok", data=events)
