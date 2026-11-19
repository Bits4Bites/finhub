import datetime
import typing
import zoneinfo

from ..models import event as models_event
from ..services import crawler_earnings as services_crawler_earnings
from ..utils import asset as asset_utils
from ..utils import conv


async def _get_upcoming_earnings_events(
    country: str,
    tz: zoneinfo.ZoneInfo,
    *,
    default_vals: dict[str, typing.Any] | None = None,
) -> list[models_event.UpcomingEarningsEvent]:
    """Convert canonical earnings rows into exchange-qualified, market-local events.

    The crawler owns validation and missing-value defaults; public wrappers own
    index filtering and company links.
    """
    country = conv.country_to_iso2(country)
    end_date = datetime.datetime.now(tz).date() + (
        datetime.timedelta(days=14) if country == "AU" else datetime.timedelta(days=7)
    )
    raw_data = (
        await services_crawler_earnings.scrape_earnings_asx(end_date)
        if country == "AU"
        else await services_crawler_earnings.scrape_earnings_us(end_date)
    )
    if raw_data.empty:
        return []

    if country == "US":
        raw_data = raw_data[raw_data["Exchange"].isin(["NASDAQ", "NYSE"])]
        if raw_data.empty:
            return []

    raw_data = raw_data.rename(
        columns={
            "Ticker": "sym",
            "Exchange": "exchange",
            "Company": "corp",
            "Announcement Date": "date",
        },
    )

    raw_data_json = raw_data.to_json(orient="records") or ""
    events = models_event.parse_upcoming_earnings_events_from_json(raw_data_json, default_vals)
    for event in events:
        event.symbol = f"{event.exchange}:{event.symbol}"
        event.timestamp_str = conv.yyyymmdd_to_iso(event.timestamp_str or "", tz) or event.timestamp_str
        if event.timestamp_str is None:
            raise ValueError("earnings announcement date must use YYYY-MM-DD format")
        event.timestamp = int(datetime.datetime.fromisoformat(event.timestamp_str).timestamp())
    return events


async def get_asx_upcoming_earnings_events(index: str = "") -> list[models_event.UpcomingEarningsEvent]:
    """Return upcoming ASX earnings announcements from today through 14 days ahead.

    Args:
        index: Optional ASX index filter. Supported values are ``ASX20``,
            ``ASX50``, ``ASX100``, ``ASX200``, and ``ASX300``; matching is
            case-insensitive. An empty value selects all available companies.

    Returns:
        A list of ``UpcomingEarningsEvent`` objects with these fields:

        - ``symbol`` (str): Security symbol in ``ASX:CODE`` form.
        - ``exchange`` (str): Always ``"ASX"``.
        - ``company_name`` (str): Issuer name, or the ticker when no name is available.
        - ``timestamp_str`` (str): Sydney midnight on the announcement date,
          as ``YYYY-MM-DD HH:MM:SS`` with a UTC offset.
        - ``timestamp`` (int): Unix seconds for that same instant.
        - ``event_category`` (str): Always ``"earnings"``.
        - ``source_name`` (str): Reporting source name.
        - ``link`` (str): Company-specific earnings-details URL.
        - ``status`` (str): Announcement status, defaulting to ``"estimated"``.
        - ``report_period`` (str): Reporting period, defaulting to ``"N/A"``.

        Returns an empty list for an unsupported index, no available
        announcements, or no matching constituents.

    Raises:
        ValueError: If required announcement fields are missing or values are
            malformed, including invalid event dates or financial values.
        KeyError: If a requested supported index is not loaded and there are
            announcements to filter.
        zoneinfo.ZoneInfoNotFoundError: If Sydney timezone data is unavailable.
        playwright.async_api.Error: If earnings retrieval cannot be started or finalized.

    Notes:
        The date window uses Australia/Sydney calendar dates and includes both
        endpoints. An index filters constituents without changing this window.
        Announcement order is preserved after filtering. Unavailable dates are
        omitted, so results may be incomplete.
    """
    asx_indices = ["ASX20", "ASX50", "ASX100", "ASX200", "ASX300"]
    normalized_index = index.upper() if index else ""
    if normalized_index and normalized_index not in asx_indices:
        return []

    country = "AU"
    tz = zoneinfo.ZoneInfo("Australia/Sydney")
    default_vals = {
        "src": "TipRanks",
        "status": "estimated",
        "report_period": "N/A",
    }
    events = await _get_upcoming_earnings_events(country, tz, default_vals=default_vals)
    if normalized_index:
        events = [e for e in events if asset_utils.is_in_index(index=normalized_index, symbol=e.symbol)]

    for event in events:
        event.link = f"https://www.tipranks.com/stocks/au:{event.symbol.lower().split(':')[-1]}/earnings"
    return events


async def get_us_upcoming_earnings_events(index: str = "") -> list[models_event.UpcomingEarningsEvent]:
    """Return upcoming US earnings announcements from today through seven days ahead.

    Args:
        index: Optional index filter. Supported values are ``NASDAQ100``,
            ``SP500``, ``SP400``, and ``SP600``; matching is case-insensitive.
            An empty value selects all available companies on supported venues.

    Returns:
        A list of ``UpcomingEarningsEvent`` objects with these fields:

        - ``symbol`` (str): Security symbol in ``EXCHANGE:CODE`` form.
        - ``exchange`` (str): ``"NASDAQ"`` or ``"NYSE"``.
        - ``company_name`` (str): Issuer name, or the ticker when no name is available.
        - ``timestamp_str`` (str): New York midnight on the announcement date,
          as ``YYYY-MM-DD HH:MM:SS`` with a UTC offset.
        - ``timestamp`` (int): Unix seconds for that same instant.
        - ``event_category`` (str): Always ``"earnings"``.
        - ``source_name`` (str): Reporting source name.
        - ``link`` (str): Company-specific earnings-details URL.
        - ``status`` (str): Announcement status, defaulting to ``"estimated"``.
        - ``report_period`` (str): Reporting period, defaulting to ``"N/A"``.

        Returns an empty list for an unsupported index, no usable
        announcements, or no matching constituents.

    Raises:
        ValueError: If required announcement fields are missing or values are
            malformed, including invalid event dates or financial values.
        KeyError: If a requested supported index is not loaded and there are
            announcements to filter.
        zoneinfo.ZoneInfoNotFoundError: If New York timezone data is unavailable.
        playwright.async_api.Error: If earnings retrieval cannot be started or finalized.

    Notes:
        The date window uses America/New_York calendar dates and includes both
        endpoints. An index filters constituents without changing this window.
        Other or unidentified venues are excluded. Announcement order is
        preserved after filtering. Unavailable dates are omitted, so results
        may be incomplete.
    """
    us_indices = ["NASDAQ100", "SP500", "SP400", "SP600"]
    normalized_index = index.upper() if index else ""
    if normalized_index and normalized_index not in us_indices:
        return []

    country = "US"
    tz = zoneinfo.ZoneInfo("America/New_York")
    default_vals = {
        "src": "TipRanks",
        "status": "estimated",
        "report_period": "N/A",
    }
    events = await _get_upcoming_earnings_events(country, tz, default_vals=default_vals)
    if normalized_index:
        events = [e for e in events if asset_utils.is_in_index(index=normalized_index, symbol=e.symbol)]

    for event in events:
        event.link = f"https://www.tipranks.com/stocks/{event.symbol.lower().split(':')[-1]}/earnings"
    return events
