import asyncio
import datetime
import random
import zoneinfo

import pandas as pd
from playwright import async_api as playwright_async_api

from . import crawler_core, market

_EARNINGS_COLUMNS = [
    "Announcement Date",
    "Exchange",
    "Ticker",
    "Company",
    "Market Cap",
    "ESP",
    "ESP Forecast",
    "Revenue",
    "Revenue Forecast",
]
_NO_EARNINGS_MESSAGE = "Currently there are no reports available for this date."


def _empty_earnings_frame() -> pd.DataFrame:
    """Return an empty frame with the shared earnings columns in order."""
    return pd.DataFrame(columns=_EARNINGS_COLUMNS)


def _parse_market_cap(value) -> int | None:
    """Expand K/M/B/T market-cap suffixes, returning null for missing markers."""
    if pd.isna(value):
        return None
    text = str(value).strip().replace("$", "").replace(",", "")
    if not text or text.upper() in {"N/A", "NA", "-"}:
        return None

    multiplier = 1
    if text[-1].upper() in {"T", "B", "M", "K"}:
        multiplier = {"T": 10**12, "B": 10**9, "M": 10**6, "K": 10**3}[text[-1].upper()]
        text = text[:-1]
    try:
        return int(float(text) * multiplier)
    except ValueError as exc:
        raise ValueError(f"invalid market capitalization: {value!r}") from exc


def _canonicalize_earnings_frame(data: pd.DataFrame) -> pd.DataFrame:
    """Copy rows into the shared column order, fill missing fields, and reset the index."""
    if data.empty:
        return _empty_earnings_frame()

    result = data.copy()
    for column in _EARNINGS_COLUMNS:
        if column not in result.columns:
            result[column] = pd.NA
    return result.loc[:, _EARNINGS_COLUMNS].reset_index(drop=True)


async def _scrape_earnings_from_tipranks(
    url_template: str,
    *,
    tz_name: str = "UTC",
    tz_info: zoneinfo.ZoneInfo | None = None,
    end_date: datetime.date,
) -> pd.DataFrame:
    """Collect TipRanks earnings from local today through the inclusive end date.

    Skip unavailable daily pages; missing required columns or malformed values fail normalization.
    """
    tz_info = tz_info if tz_info else zoneinfo.ZoneInfo(tz_name)
    urls = []
    dates = []
    current_date = datetime.datetime.now(tz_info).date()
    while current_date <= end_date:
        urls.append(url_template.format(date=current_date.strftime("%Y-%m-%d")))
        dates.append(current_date.strftime("%Y-%m-%d"))
        current_date += datetime.timedelta(days=1)
    page_content_list = await crawler_core.fetch_multi_webpages_content_playwright(
        urls,
        delay_between_requests=1.5,
    )
    frames = []
    for index, page_content in enumerate(page_content_list):
        if page_content is None:
            continue
        page_df = crawler_core.extract_data_table_from_html(page_content)
        if page_df.empty:
            continue
        page_df = page_df[page_df.iloc[:, 0] != _NO_EARNINGS_MESSAGE].copy()
        if page_df.empty:
            continue
        page_df["Announcement Date"] = dates[index]
        frames.append(page_df)

    if not frames:
        return _empty_earnings_frame()

    df = pd.concat(frames, ignore_index=True)
    cols_to_remove = ["Price", "% Change", "Time", "Analyst Consensus", "Smart Score", "Follow"]
    df = df.drop(columns=cols_to_remove, errors="ignore")
    df = df.rename(columns={"Name": "Ticker"})

    df["Market Cap"] = df["Market Cap"].apply(_parse_market_cap)
    return _canonicalize_earnings_frame(df)


async def scrape_earnings_asx(end_date: datetime.date) -> pd.DataFrame:
    """Return upcoming Australian earnings announcements from today through ``end_date``.

    Args:
        end_date: Inclusive final calendar date in Australia/Sydney time.

    Returns:
        A DataFrame with the canonical columns ``Ticker``, ``Company``,
        ``Exchange``, and ``Announcement Date``. Dates use ``YYYY-MM-DD``;
        No announcements, failed pages, or an end date before today produce an
        empty DataFrame with those columns.

    Raises:
        ZoneInfoNotFoundError: If the configured Australia/Sydney timezone is unavailable.
        ValueError: If a returned source row cannot be normalized to the
            canonical contract.
    """
    url_template = "https://www.tipranks.com/calendars/earnings/{date}/australia"
    tz = "Australia/Sydney"
    df = await _scrape_earnings_from_tipranks(url_template, tz_name=tz, end_date=end_date)
    df["Exchange"] = "ASX"
    df["Currency"] = "AUD"
    return _canonicalize_earnings_frame(df)


async def scrape_earnings_us(end_date: datetime.date) -> pd.DataFrame:
    """Return upcoming US earnings announcements from TipRanks.

    Args:
        end_date: Inclusive final announcement date in New York time.

    Returns:
        Browser-rendered normalized earnings rows, including ``Exchange Name``
        when TipRanks exposes it, or an empty DataFrame when no rows are
        available.

    Raises:
        ZoneInfoNotFoundError: If the configured New York timezone is
            unavailable.
        ValueError: If a non-empty source table does not identify a symbol.

    Notes:
        The browser callback requests TipRanks' optional exchange column so the
        event service can exclude unsupported US venues.
    """
    url_template = "https://www.tipranks.com/calendars/earnings/{date}"
    tz = "America/New_York"
    df = await _scrape_earnings_from_tipranks(url_template, tz_name=tz, end_date=end_date)
    df["Currency"] = "USD"

    def _lookup_exchange(ticker: str) -> str:
        """Resolve the exchange from loaded US constituents, or return "N/A"."""
        company = market.market_indices.revert_lookup_company("US", ticker)
        return company.extract_exchange_code()[0] if company else "N/A"

    df["Exchange"] = df["Ticker"].apply(_lookup_exchange)
    return _canonicalize_earnings_frame(df)
