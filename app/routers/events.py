import logging
import urllib.parse

from fastapi import APIRouter, Query
from fastapi.responses import RedirectResponse

from .. import config
from ..schemas import events as schemas_event
from ..services import event as services_event
from ..services import msai_asx_listings as services_asx_listings
from ..utils import conv

router = APIRouter(prefix="/events", tags=["events"])


@router.get(
    "/upcoming_dividends", response_model=schemas_event.UpcomingDividendsResponse, response_model_exclude_none=True
)
async def get_upcoming_dividends_event(
    country: str = Query(description="Country code to filter events by (only 'AU', 'US' and 'VN' are supported)."),
    index: str = Query(
        "",
        description="Optional stock index to filter events by (support 'ASX20', 'ASX50', 'ASX100', 'ASX200', 'ASX300', 'NASDAQ100', 'SP500', 'SP400', 'SP600', 'VN30', 'VN100').",
    ),
) -> schemas_event.UpcomingDividendsResponse | RedirectResponse:
    """
    Check for upcoming dividend/distribution events for a market.
    """
    if config.settings_finhub_proxy.proxy_mode.upper() == "REDIRECT":
        proxy_url = config.settings_finhub_proxy.url_web_crawl_node.rstrip("/")
        prefix = str(router.prefix)
        e_country = urllib.parse.quote(country, safe="")
        e_index = urllib.parse.quote(index, safe="")
        next_url = f"{proxy_url}{prefix}/upcoming_dividends?country={e_country}&index={e_index}"
        next_url_for_log = urllib.parse.quote(next_url, safe="")
        logging.info(f"Redirecting request to {next_url_for_log}")
        return RedirectResponse(url=next_url, status_code=307)

    country = conv.country_to_iso2(country)
    match country:
        case "AU":
            events = await services_event.get_asx_upcoming_dividends_events(index)
        case "US":
            events = await services_event.get_us_upcoming_dividends_events(index)
        case "VN":
            events = await services_event.get_vn_upcoming_dividends_events(index)
        case _:
            return schemas_event.UpcomingDividendsResponse(status=501, message=f"Unsupported country '{country}'")

    from ..utils import asset as asset_utils

    for event in events:
        for index in ["ASX300", "NASDAQ100", "SP500", "SP400", "VN100"]:
            if asset_utils.is_in_index(index=index, symbol=event.symbol):
                event_date = event.date[:10] if event.date else ""
                logging.info(
                    f"Upcoming dividend event: {event.symbol} ({index}) / {event_date} / {event.amount} ({event.dividend_yield:.2%})"
                )
                event.analysis = await services_event.analyse_dividend_event(
                    symbol=event.symbol, div_amount=event.amount or 0, ex_date=event.date[:10] if event.date else ""
                )
                break

    return schemas_event.UpcomingDividendsResponse(status=200, message="ok", data=events)


@router.get(
    "/upcoming_earnings", response_model=schemas_event.UpcomingEarningsResponse, response_model_exclude_none=True
)
async def get_upcoming_earnings_event(
    country: str = Query(description="Country code to filter events by (only 'AU' and 'US' are supported)."),
    index: str = Query(
        "",
        description="Optional stock index to filter events by (support 'ASX20', 'ASX50', 'ASX100', 'ASX200', 'ASX300', 'NASDAQ100', 'SP500', 'SP400', 'SP600').",
    ),
) -> schemas_event.UpcomingEarningsResponse | RedirectResponse:
    """
    Check for upcoming earnings events for a market.
    """
    if config.settings_finhub_proxy.proxy_mode.upper() == "REDIRECT":
        proxy_url = config.settings_finhub_proxy.url_web_crawl_node.rstrip("/")
        prefix = str(router.prefix)
        e_country = urllib.parse.quote(country, safe="")
        e_index = urllib.parse.quote(index, safe="")
        next_url = f"{proxy_url}{prefix}/upcoming_earnings?country={e_country}&index={e_index}"
        next_url_for_log = urllib.parse.quote(next_url, safe="")
        logging.info(f"Redirecting request to {next_url_for_log}")
        return RedirectResponse(url=next_url, status_code=307)

    country = conv.country_to_iso2(country)
    match country:
        case "AU":
            events = await services_event.get_asx_upcoming_earnings_events(index)
        case "US":
            events = await services_event.get_us_upcoming_earnings_events(index)
        case _:
            return schemas_event.UpcomingEarningsResponse(status=501, message=f"Unsupported country '{country}'")

    return schemas_event.UpcomingEarningsResponse(status=200, message="ok", data=events)


@router.get("/new_listings", response_model=schemas_event.ListingsResponse, response_model_exclude_none=True)
async def get_new_listings(
    country: str = Query("", description="Country code to filter events by (only 'AU' is supported)."),
) -> schemas_event.ListingsResponse | RedirectResponse:
    """
    Check for new listing events for a market, using AI assistance.
    Note: currently only AU is supported.
    """
    if config.settings_finhub_proxy.proxy_mode.upper() == "REDIRECT":
        proxy_url = config.settings_finhub_proxy.url_web_crawl_node.rstrip("/")
        prefix = str(router.prefix)
        e_country = urllib.parse.quote(country, safe="")
        next_url = f"{proxy_url}{prefix}/new_listings?country={e_country}"
        next_url_for_log = urllib.parse.quote(next_url, safe="")
        logging.info(f"Redirecting request to {next_url_for_log}")
        return RedirectResponse(url=next_url, status_code=307)

    country = conv.country_to_iso2(country)
    match country:
        case "AU":
            events = await services_asx_listings.ai_get_asx_new_listings()
        case _:
            return schemas_event.ListingsResponse(status=501, message=f"Unsupported country '{country}'")

    return schemas_event.ListingsResponse(status=200, message="ok", data=events)
