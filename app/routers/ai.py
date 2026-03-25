from fastapi import APIRouter, Query

from ..schemas import finhub as schemas
from ..services import ai as ai_service

router = APIRouter(prefix="/ai", tags=["ai"])


@router.get(
    "/analyze_dividend_event",
    response_model=schemas.AnalyzeDividendEventResponse,
    response_model_exclude_none=True,
)
async def analyse_dividend_event(
    symbol: str = Query(description="The stock symbol"),
    ex_date: str = Query(description="Ex-Dividend date in format YYYY-MM-DD"),
    div_amount: float = Query(description="The dividend amount as float number, without currency symbol"),
) -> schemas.AnalyzeDividendEventResponse:
    """
    Analyzes a dividend event.
    """
    result = await ai_service.ai_analyse_dividend_event(symbol=symbol, ex_date=ex_date, div_amount=div_amount)
    if result is None:
        return schemas.AnalyzeDividendEventResponse(status=400, message="Invalid inputs or stock not found")
    return schemas.AnalyzeDividendEventResponse(status=200, message="ok", data=result)


# @router.get(
#     "/event/upcoming_dividends", response_model=schemas.UpcomingDividendsResponse, response_model_exclude_none=True
# )
# async def get_upcoming_dividends_event(
#     country: str = Query(description="Country code to filter events by (only 'AU, 'US' and 'VN' are supported)."),
#     index: str = Query(
#         "",
#         description="Optional stock index to filter events by (support 'NASDAQ100', 'SP500', 'SP400', 'SP600', 'ASX20', 'ASX50', 'ASX100', 'ASX200' and 'ASX300').",
#     ),
# ) -> schemas.UpcomingDividendsResponse:
#     """
#     Check for upcoming dividend/distribution events for a market, using AI assistance.
#     """
#     country = country.upper()
#     match country:
#         case "AU" | "AUS" | "AUSTRALIA":
#             events = await stock_service.get_asx_upcoming_dividends_events(index)
#             # events = (
#             #     await ai_service.ai_get_asx_upcoming_dividends_events(index)
#             #     if index
#             #     else await stock_service.get_asx_upcoming_dividends_events()
#             # )
#         case "US" | "USA" | "UNITED STATES":
#             events = await stock_service.get_us_upcoming_dividends_events(index)
#             # events = (
#             #     await ai_service.ai_get_us_upcoming_dividends_events(index)
#             #     if index
#             #     else await stock_service.get_us_upcoming_dividends_events()
#             # )
#         case "VN" | "VIETNAM":
#             events = await stock_service.get_vn_upcoming_dividends_events(index)
#             # events = (
#             #     await ai_service.ai_get_vn_upcoming_dividends_events(index)
#             #     if index
#             #     else await stock_service.get_vn_upcoming_dividends_events()
#             # )
#         case _:
#             return schemas.UpcomingDividendsResponse(status=501, message=f"Unsupported country '{country}'")
#
#     return schemas.UpcomingDividendsResponse(status=200, message="ok", data=events)
#
#
# @router.get(
#     "/event/upcoming_earnings", response_model=schemas.UpcomingEarningsResponse, response_model_exclude_none=True
# )
# async def get_upcoming_earnings_event(
#     country: str = Query(description="Country code to filter events by (only 'AU, 'US' and 'VN' are supported)."),
#     index: str = Query(
#         "",
#         description="Optional stock index to filter events by (support 'NASDAQ100', 'SP500', 'SP400', 'SP600', 'ASX20', 'ASX50', 'ASX100', 'ASX200' and 'ASX300').",
#     ),
# ) -> schemas.UpcomingEarningsResponse:
#     """
#     Check for upcoming earnings events for a market, using AI assistance.
#     """
#     country = country.upper()
#     match country:
#         case "AU" | "AUS" | "AUSTRALIA":
#             events = await stock_service.get_asx_upcoming_earnings_events(index)
#             # events = (
#             #     await ai_service.ai_get_asx_upcoming_earnings_events(index)
#             #     if index
#             #     else await stock_service.get_asx_upcoming_earnings_events()
#             # )
#         case "US" | "USA" | "UNITED STATES":
#             events = await stock_service.get_us_upcoming_earnings_events(index)
#             # events = (
#             #     await ai_service.ai_get_us_upcoming_earnings_events(index)
#             #     if index
#             #     else await stock_service.get_us_upcoming_earnings_events()
#             # )
#         case _:
#             return schemas.UpcomingEarningsResponse(status=501, message=f"Unsupported country '{country}'")
#
#     return schemas.UpcomingEarningsResponse(status=200, message="ok", data=events)
#
#
# @router.get("/event/new_listings", response_model=schemas.ListingsResponse, response_model_exclude_none=True)
# async def get_new_listings(
#     country: str = Query("", description="Country code to filter events by (e.g., 'AU', 'US', 'VN', etc.)."),
# ) -> schemas.ListingsResponse:
#     """
#     Check for new listing events for a market, using AI assistance.
#     Note: currently only AU is supported.
#     """
#     country = country.upper()
#     match country:
#         case "AU" | "AUS" | "AUSTRALIA":
#             events = await ai_service.ai_get_asx_new_listings()
#         case _:
#             return schemas.ListingsResponse(status=501, message=f"Unsupported country '{country}'")
#
#     return schemas.ListingsResponse(status=200, message="ok", data=events)
