import datetime
import typing
import zoneinfo

from ..models import event as models_event
from ..services import crawler_earnings as services_crawler_earnings
from ..utils import asset as asset_utils
from ..utils import conv


def _calc_end_date_to_fetch_events(*, event_type: str, tz: zoneinfo.ZoneInfo, index: str = ""):
    today = datetime.datetime.now(tz).date()
    if index:  # if index is provided to filter events, we look further into the future to capture more relevant events
        if "EARNINGS" in event_type.upper():
            end_date = today + datetime.timedelta(days=10)
        else:
            end_date = today + datetime.timedelta(days=14)
    else:  # if no index filter is provided, we can look at a shorter time window for more immediate events
        end_date = today + datetime.timedelta(days=7)
    return end_date


async def _get_upcoming_earnings_events(
    country: str, tz: zoneinfo.ZoneInfo, *, default_vals: dict[str, typing.Any] | None = None, index: str = ""
) -> list[models_event.UpcomingEarningsEvent]:
    country = conv.country_to_iso2(country)
    end_date = _calc_end_date_to_fetch_events(event_type="EARNINGS", tz=tz, index=index)
    raw_data = (
        await services_crawler_earnings.scrape_earnings_asx(end_date)
        if country == "AU"
        else await services_crawler_earnings.scrape_earnings_us(end_date)
    )
    if raw_data.empty:
        return []

    required_columns = {"Symbol", "Announcement Date"}
    missing_columns = required_columns.difference(raw_data.columns)
    if missing_columns:
        raise ValueError(f"earnings data is missing columns: {sorted(missing_columns)}")
    if country == "US" and "Exchange Name" not in raw_data.columns:
        raise ValueError("US earnings data is missing the Exchange Name column")

    raw_data = raw_data.copy()
    if "Url" in raw_data.columns:
        raw_data = raw_data.drop(columns=["Url"])

    if "Company Name" not in raw_data.columns and "Company" not in raw_data.columns:
        raw_data["Company Name"] = raw_data["Symbol"]

    if country == "US":
        raw_data = raw_data[raw_data["Exchange Name"].isin(["NASDAQ", "NYSE"])].copy()
        if raw_data.empty:
            return []

    raw_data = raw_data.rename(
        columns={
            "Symbol": "sym",
            "Exchange Name": "exchange",
            "Company Name": "corp",
            "Company": "corp",
            "Announcement Date": "date",
        },
    )

    raw_data_json = raw_data.to_json(orient="records") or ""
    events = models_event.parse_upcoming_earnings_events_from_json(raw_data_json, default_vals)
    for event in events:
        event.symbol = f"{event.exchange}:{event.symbol}"
        event.timestamp_str = conv.yyyymmdd_to_iso(event.timestamp_str or "", tz)
        if event.timestamp_str is None:
            raise ValueError("earnings announcement date must use YYYY-MM-DD format")
        event.timestamp = int(datetime.datetime.fromisoformat(event.timestamp_str).timestamp())
    return events


async def get_asx_upcoming_earnings_events(index: str = "") -> list[models_event.UpcomingEarningsEvent]:
    """Return normalized upcoming earnings events for ASX companies.

    Args:
        index: Optional ASX index filter. Supported values are ``ASX20``,
            ``ASX50``, ``ASX100``, ``ASX200``, and ``ASX300``; matching is
            case-insensitive.

    Returns:
        Earnings events with ``ASX:``-qualified symbols, timezone-aware
        timestamps, TipRanks provenance, and per-company TipRanks links.
        Missing source values default to status ``estimated`` and report
        period ``N/A``.
        Returns an empty list for an unsupported index or when no matching
        announcements are available.

    Raises:
        ValueError: If non-empty crawler data lacks required symbol or date
            fields.
        KeyError: If a requested supported index is not loaded.

    Notes:
        Supplying an index extends the crawler window and filters the normalized
        events to that index's constituents. Source order is preserved after
        filtering.
    """
    asx_indices = ["ASX20", "ASX50", "ASX100", "ASX200", "ASX300"]
    index = index.upper()
    if index and index not in asx_indices:
        return []

    country = "AU"
    tz = zoneinfo.ZoneInfo("Australia/Sydney")
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
    """Return normalized upcoming earnings events for major US exchanges.

    Args:
        index: Optional index filter. Supported values are ``NASDAQ100``,
            ``SP500``, ``SP400``, and ``SP600``; matching is case-insensitive.

    Returns:
        NASDAQ and NYSE earnings events with exchange-qualified symbols,
        timezone-aware timestamps, TipRanks provenance, and per-company
        TipRanks links. Missing source values default to status ``estimated``
        and report period ``N/A``. Returns an empty list for an unsupported
        index or when no matching announcements are available.

    Raises:
        ValueError: If non-empty crawler data lacks required symbol, exchange,
            or date fields.
        KeyError: If a requested supported index is not loaded.

    Notes:
        Other US venues are excluded. Supplying an index extends the crawler
        window and filters the normalized events to that index's constituents.
        Source order is preserved after filtering.
    """
    us_indices = ["NASDAQ100", "SP500", "SP400", "SP600"]
    index = index.upper()
    if index and index not in us_indices:
        return []

    country = "US"
    tz = zoneinfo.ZoneInfo("America/New_York")
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
