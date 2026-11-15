from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from ..models import event as models_event
from ..services import crawler_earnings as services_crawler_earnings
from ..utils import asset as asset_utils
from ..utils import conv


def _calc_end_date_to_fetch_events(*, event_type: str, tz: ZoneInfo, index: str = ""):
    today = datetime.now(tz).date()
    if index:  # if index is provided to filter events, we look further into the future to capture more relevant events
        if "EARNINGS" in event_type.upper():
            end_date = today + timedelta(days=10)
        else:
            end_date = today + timedelta(days=14)
    else:  # if no index filter is provided, we can look at a shorter time window for more immediate events
        end_date = today + timedelta(days=7)
    return end_date


async def _get_upcoming_earnings_events(
    country: str, tz: ZoneInfo, *, default_vals: dict[str, Any] = None, index: str = ""
) -> list[models_event.UpcomingEarningsEvent]:
    """
    Check for upcoming earnings events (AU  & US only).

    Args:
        country (str): Country code to filter events by (e.g., 'AU', 'US', etc.).
        tz (ZoneInfo): Timezone to use for date calculations.
        default_vals (str, optional): internal use
        index (str, optional): internal use

    Returns:
        list[models_event.UpcomingEarningsEvent]: A list of upcoming earnings events
    """
    country = conv.country_to_iso2(country)
    end_date = _calc_end_date_to_fetch_events(event_type="EARNINGS", tz=tz, index=index)
    raw_data = (
        await services_crawler_earnings.scrape_earnings_asx(end_date)
        if country == "AU"
        else await services_crawler_earnings.scrape_earnings_us(end_date)
    )
    if raw_data.empty:
        return []

    # optimize tokens:
    # - Removing column "Url"
    if "Url" in raw_data.columns:
        raw_data = raw_data.drop(columns=["Url"])

    # US market: remove rows where "Exchange Name" is not "NASDAQ" or "NYSE"
    if country == "US" or country == "USA" or country == "UNITED STATES":
        if "Exchange Name" in raw_data.columns:
            raw_data = raw_data[raw_data["Exchange Name"].isin(["NASDAQ", "NYSE"])]

    # final transformation of raw_data
    # - rename column Symbol to sym
    # - rename column Exchange Name to exchange
    # - rename column Company Name to corp
    # - rename column Announcement Date to date
    raw_data.rename(
        columns={
            "Symbol": "sym",
            "Exchange Name": "exchange",
            "Company Name": "corp",
            "Company": "corp",
            "Announcement Date": "date",
        },
        inplace=True,
    )

    raw_data_json = raw_data.to_json(orient="records") or ""
    events = models_event.parse_upcoming_earnings_events_from_json(raw_data_json, default_vals)
    for event in events:
        event.symbol = f"{event.exchange}:{event.symbol}"
        event.timestamp_str = conv.yyyymmdd_to_iso(event.timestamp_str or "", tz)
        event.timestamp = int(datetime.fromisoformat(event.timestamp_str or "").timestamp())
    return events


async def get_asx_upcoming_earnings_events(index: str = "") -> list[models_event.UpcomingEarningsEvent]:
    """
    Check for upcoming earnings events for ASX.

    Args:
        index (str, optional): ASX index to filter stocks (e.g. ASX20, ASX50, ASX100, ASX200 and ASX300)

    Returns:
        list[models_event.UpcomingEarningsEvent]: A list of upcoming earnings events
    """
    asx_indices = ["ASX20", "ASX50", "ASX100", "ASX200", "ASX300"]
    index = index.upper()
    if index and index not in asx_indices:
        return []

    country = "AU"
    tz = ZoneInfo("Australia/Sydney")
    default_vals = {
        "exchange": "ASX",
        "src": "TipRanks",
        "status": "estimated",
        "report_period": "N/A",
    }
    events = await _get_upcoming_earnings_events(country, tz, default_vals=default_vals, index=index)
    if index:
        events = [e for e in events if asset_utils.is_in_index(index=index, symbol=e.symbol)]

    for event in events:
        event.link = f"https://www.tipranks.com/stocks/au:{event.symbol.lower().split(':')[-1]}/earnings"
    return events


async def get_us_upcoming_earnings_events(index: str = "") -> list[models_event.UpcomingEarningsEvent]:
    """
    Check for upcoming earnings events for US market.

    Args:
        index (str, optional): index to filter stocks (e.g. NASDAQ100, SP500, SP400 and SP600)

    Returns:
        list[models_event.UpcomingEarningsEvent]: A list of upcoming earnings events
    """
    us_indices = ["NASDAQ100", "SP500", "SP400", "SP600"]
    index = index.upper()
    if index and index not in us_indices:
        return []

    country = "US"
    tz = ZoneInfo("America/New_York")
    default_vals = {
        "src": "TipRanks",
        "status": "estimated",
        "report_period": "N/A",
    }
    events = await _get_upcoming_earnings_events(country, tz, default_vals=default_vals, index=index)
    if index:
        events = [e for e in events if asset_utils.is_in_index(index=index, symbol=e.symbol)]

    for event in events:
        event.link = f"https://www.tipranks.com/stocks/{event.symbol.lower().split(':')[-1]}/earnings"
    return events
