import logging

from fastapi import APIRouter, Query, Request
from fastapi.responses import RedirectResponse

from app.schemas.finhub import UpcomingDividendsResponse, UpcomingEarningsResponse, ListingsResponse
from ..schemas import finhub as schemas
from ..services import ai as ai_service, stock as stock_service
from ..utils import finhub as finhub_utils
from ..config import settings_finhub_proxy

router = APIRouter(prefix="/events", tags=["events"])


@router.get("/upcoming_dividends", response_model=schemas.UpcomingDividendsResponse, response_model_exclude_none=True)
async def get_upcoming_dividends_event(
    request: Request,
    country: str = Query(description="Country code to filter events by (only 'AU', 'US' and 'VN' are supported)."),
    index: str = Query(
        "",
        description="Optional stock index to filter events by (support 'ASX20', 'ASX50', 'ASX100', 'ASX200', 'ASX300', 'NASDAQ100', 'SP500', 'SP400', 'SP600', 'VN30' and 'VN100').",
    ),
) -> UpcomingDividendsResponse | RedirectResponse:
    """
    Check for upcoming dividend/distribution events for a market.
    """
    if settings_finhub_proxy.proxy_mode.upper() == "REDIRECT":
        proxy_url = settings_finhub_proxy.url_web_crawl_node.rstrip("/")
        prefix = str(router.prefix)
        next_url = f"{proxy_url}{prefix}/upcoming_dividends?country={country}&index={index}"
        logging.info(f"Redirecting request to {next_url}")
        return RedirectResponse(url=next_url, status_code=307)

    country = country.upper()
    match country:
        case "AU" | "AUS" | "AUSTRALIA":
            events = await stock_service.get_asx_upcoming_dividends_events(index)
        case "US" | "USA" | "UNITED STATES":
            events = await stock_service.get_us_upcoming_dividends_events(index)
        case "VN" | "VIETNAM":
            events = await stock_service.get_vn_upcoming_dividends_events(index)
        case _:
            return schemas.UpcomingDividendsResponse(status=501, message=f"Unsupported country '{country}'")

    for event in events:
        for index in ["ASX300", "NASDAQ100", "SP500", "SP400", "VN100"]:
            if finhub_utils.is_in_index(index=index, symbol=event.symbol):
                logging.info(
                    f"Upcoming dividend event: {event.symbol} ({index}) / {event.date[:10]} / {event.amount} ({event.dividend_yield:.2%})"
                )
                event.analysis = await stock_service.analyse_dividend_event(
                    symbol=event.symbol, div_amount=event.amount, ex_date=event.date[:10]
                )
                break

    return schemas.UpcomingDividendsResponse(status=200, message="ok", data=events)


@router.get("/upcoming_earnings", response_model=schemas.UpcomingEarningsResponse, response_model_exclude_none=True)
async def get_upcoming_earnings_event(
    country: str = Query(description="Country code to filter events by (only 'AU', 'US' and 'VN' are supported)."),
    index: str = Query(
        "",
        description="Optional stock index to filter events by (support 'ASX20', 'ASX50', 'ASX100', 'ASX200', 'ASX300', 'NASDAQ100', 'SP500', 'SP400', 'SP600', 'VN30' and 'VN100').",
    ),
) -> UpcomingEarningsResponse | RedirectResponse:
    """
    Check for upcoming earnings events for a market.
    """
    if settings_finhub_proxy.proxy_mode.upper() == "REDIRECT":
        proxy_url = settings_finhub_proxy.url_web_crawl_node.rstrip("/")
        prefix = str(router.prefix)
        next_url = f"{proxy_url}{prefix}/upcoming_earnings?country={country}&index={index}"
        logging.info(f"Redirecting request to {next_url}")
        return RedirectResponse(url=next_url, status_code=307)

    country = country.upper()
    match country:
        case "AU" | "AUS" | "AUSTRALIA":
            events = await stock_service.get_asx_upcoming_earnings_events(index)
        case "US" | "USA" | "UNITED STATES":
            events = await stock_service.get_us_upcoming_earnings_events(index)
        case _:
            return schemas.UpcomingEarningsResponse(status=501, message=f"Unsupported country '{country}'")

    return schemas.UpcomingEarningsResponse(status=200, message="ok", data=events)


@router.get("/new_listings", response_model=schemas.ListingsResponse, response_model_exclude_none=True)
async def get_new_listings(
    country: str = Query("", description="Country code to filter events by (only 'AU' is supported)."),
) -> ListingsResponse | RedirectResponse:
    """
    Check for new listing events for a market, using AI assistance.
    Note: currently only AU is supported.
    """
    if settings_finhub_proxy.proxy_mode.upper() == "REDIRECT":
        proxy_url = settings_finhub_proxy.url_web_crawl_node.rstrip("/")
        prefix = str(router.prefix)
        next_url = f"{proxy_url}{prefix}/new_listings?country={country}"
        logging.info(f"Redirecting request to {next_url}")
        return RedirectResponse(url=next_url, status_code=307)

    country = country.upper()
    match country:
        case "AU" | "AUS" | "AUSTRALIA":
            events = await ai_service.ai_get_asx_new_listings()
        case _:
            return schemas.ListingsResponse(status=501, message=f"Unsupported country '{country}'")

    return schemas.ListingsResponse(status=200, message="ok", data=events)
