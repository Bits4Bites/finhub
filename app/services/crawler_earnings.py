import datetime
import decimal
import math
import zoneinfo

import pandas as pd

from . import crawler_core, market

_EARNINGS_COLUMNS = [
    "Announcement Date",
    "Exchange",
    "Ticker",
    "Company",
    "Market Cap",
    "EPS",
    "EPS Forecast",
    "Revenue",
    "Revenue Forecast",
    "Currency",
]
_EARNINGS_NUMERIC_DEFAULTS = {
    "Market Cap": 0,
    "EPS": 0.0,
    "EPS Forecast": 0.0,
    "Revenue": 0,
    "Revenue Forecast": 0,
}
_NO_EARNINGS_MESSAGE = "Currently there are no reports available for this date."
_MISSING_NUMERIC_MARKERS = {"", "N/A", "NA", "NAN", "-", "--", "\u2013", "\u2014", "\u2015"}


def _empty_earnings_frame() -> pd.DataFrame:
    """Return an empty frame with the shared earnings columns in order."""
    return pd.DataFrame(columns=_EARNINGS_COLUMNS)


def _canonicalize_earnings_frame(data: pd.DataFrame) -> pd.DataFrame:
    """Copy canonical columns, zero-fill missing numerics, and reset the index.

    Ticker validation and formatted-number parsing remain the caller's responsibility.
    """
    if data.empty:
        return _empty_earnings_frame()

    result = data.copy()
    for column in _EARNINGS_COLUMNS:
        if column not in result.columns:
            result[column] = _EARNINGS_NUMERIC_DEFAULTS.get(column, pd.NA)
    for column, default in _EARNINGS_NUMERIC_DEFAULTS.items():
        values = result[column]
        if pd.api.types.is_string_dtype(values.dtype):
            values = values.astype(object)
        result[column] = values.fillna(default)
    return result.loc[:, _EARNINGS_COLUMNS].reset_index(drop=True)


def _validate_required_earnings_fields(data: pd.DataFrame) -> None:
    """Reject missing ticker headers and blank/null ticker values before merging pages."""
    if "Ticker" not in data.columns:
        raise ValueError("Earnings table is missing columns: ['Ticker']")
    tickers = data["Ticker"]
    if tickers.isna().any() or tickers.astype(str).str.strip().eq("").any():
        raise ValueError("Earnings table has missing values in required columns: ['Ticker']")


def _normalize_money_text(value) -> str:
    """Normalize supported currency prefixes, commas, and negative notation.

    Map nulls/placeholders to ``"0"``; preserve signed or parenthesized negatives.
    Leave numeric validation to the amount parsers.
    """
    if pd.isna(value):
        return "0"
    text = str(value).strip().replace(",", "").replace("\u2212", "-")
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1].strip()
    sign = ""
    if text.startswith(("+", "-")):
        sign, text = text[0], text[1:].lstrip()
    for prefix in ("AU$", "US$", "$"):
        if text.upper().startswith(prefix):
            text = text[len(prefix) :].strip()
            break
    return "0" if text.upper() in _MISSING_NUMERIC_MARKERS else sign + text


def _parse_money_amount(value) -> float:
    """Parse signed, finite per-share amounts, defaulting missing values to ``0.0``.

    Raise ``ValueError`` for malformed or non-finite amounts.
    """
    try:
        amount = float(_normalize_money_text(value))
        if not math.isfinite(amount):
            raise ValueError("amount must be finite")
        return amount
    except ValueError as exc:
        raise ValueError(f"invalid amount: {value!r}") from exc


def _parse_market_cap(value) -> int:
    """Parse market cap or revenue as whole currency units using decimal K/M/B/T scaling.

    Default missing values to zero, truncate fractional units toward zero, and
    raise ``ValueError`` for malformed or non-finite amounts.
    """
    text = _normalize_money_text(value)
    multiplier = 1
    if text[-1].upper() in {"T", "B", "M", "K"}:
        multiplier = {"T": 10**12, "B": 10**9, "M": 10**6, "K": 10**3}[text[-1].upper()]
        text = text[:-1]
    try:
        amount = decimal.Decimal(text) * multiplier
        if not amount.is_finite():
            raise ValueError("amount must be finite")
        return int(amount)
    except (decimal.DecimalException, ValueError, OverflowError) as exc:
        raise ValueError(f"invalid monetary value: {value!r}") from exc


async def _scrape_earnings_from_tipranks(
    url_template: str,
    *,
    tz_name: str = "UTC",
    tz_info: zoneinfo.ZoneInfo | None = None,
    end_date: datetime.date,
) -> pd.DataFrame:
    """Collect TipRanks earnings from local today through the inclusive ``end_date``.

    ``tz_info`` overrides ``tz_name``. Skip unavailable dates, reject malformed
    data, and validate tickers per page before merging and canonicalizing once.
    Missing actual/forecast values independently use zero; market wrappers
    supply exchange and currency.
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
    rename_map = {
        "Name": "Ticker",
        "Company Name": "Company",
    }
    for index, page_content in enumerate(page_content_list):
        if page_content is None:
            continue
        page_df = crawler_core.extract_data_table_from_html(page_content)
        if page_df.empty:
            continue
        page_df = page_df[page_df.iloc[:, 0].ne(_NO_EARNINGS_MESSAGE).fillna(True)].copy()
        if page_df.empty:
            continue
        page_df = page_df.rename(
            columns={source: target for source, target in rename_map.items() if target not in page_df.columns}
        )
        _validate_required_earnings_fields(page_df)
        for source_column, actual_column, forecast_column in (
            ("EPS / Forecast", "EPS", "EPS Forecast"),
            ("Revenue / Forecast", "Revenue", "Revenue Forecast"),
        ):
            if source_column not in page_df.columns:
                continue
            # Keep the slash in the missing marker from becoming the pair separator.
            parts = (
                page_df[source_column]
                .astype("string")
                .str.replace("N/A", "NA", case=False, regex=False)
                .str.split("/", n=1, expand=True)
                .reindex(columns=[0, 1])
            )
            page_df[actual_column] = parts[0]
            page_df[forecast_column] = parts[1]
        page_df["Announcement Date"] = dates[index]
        frames.append(page_df)

    if not frames:
        return _empty_earnings_frame()

    df = _canonicalize_earnings_frame(pd.concat(frames, ignore_index=True))
    missing_company = df["Company"].isna() | df["Company"].astype(str).str.strip().eq("")
    df["Company"] = df["Company"].mask(missing_company, df["Ticker"])
    for column in ("EPS", "EPS Forecast"):
        df[column] = df[column].apply(_parse_money_amount)
    for column in ("Market Cap", "Revenue", "Revenue Forecast"):
        df[column] = df[column].apply(_parse_market_cap)
    return df


async def scrape_earnings_asx(end_date: datetime.date) -> pd.DataFrame:
    """Return ASX earnings announcements scheduled from today through ``end_date``.

    Args:
        end_date (datetime.date): Inclusive final announcement date. The date
            window uses ``Australia/Sydney`` local calendar dates.

    Returns:
        A DataFrame with one row per earnings announcement and a contiguous,
        zero-based index. Returned rows contain no null fields. Columns, in order:

        - ``Announcement Date`` (str): Announcement date as ``YYYY-MM-DD``.
        - ``Exchange`` (str): Always ``"ASX"``.
        - ``Ticker`` (str): Security code, such as ``"CBA"``.
        - ``Company`` (str): Issuer name, with the ticker as fallback for absent or blank names.
        - ``Market Cap`` (int): Company market capitalization in whole AUD.
        - ``EPS`` (float): Reported earnings per share in AUD; may be negative.
        - ``EPS Forecast`` (float): Forecast earnings per share in AUD; may be negative.
        - ``Revenue`` (int): Reported revenue in whole AUD.
        - ``Revenue Forecast`` (int): Forecast revenue in whole AUD.
        - ``Currency`` (str): Always ``"AUD"``.

        Rows are grouped by ascending announcement date; order within a date
        is unspecified. No available announcements, or an end date before
        local today, produce an empty DataFrame retaining all columns.

    Raises:
        zoneinfo.ZoneInfoNotFoundError: If Australia/Sydney timezone data is unavailable.
        ValueError: If earnings data is malformed, including missing/blank
            tickers or invalid/non-finite financial values.
        playwright.async_api.Error: If earnings retrieval cannot be started or finalized.

    Notes:
        Missing numeric fields and individual actual/forecast components default
        independently to zero: ``0.0`` for EPS fields and ``0`` for other numeric
        fields. A zero does not distinguish an unavailable value from an actual zero.
        Market capitalization and revenues use whole currency units; fractional
        units are discarded toward zero.

        Unavailable dates are omitted, so results may be incomplete. An empty
        result does not distinguish no announcements from unavailable data.
    """
    url_template = "https://www.tipranks.com/calendars/earnings/{date}/australia"
    tz = "Australia/Sydney"
    df = await _scrape_earnings_from_tipranks(url_template, tz_name=tz, end_date=end_date)
    if df.empty:
        return df

    df["Exchange"] = "ASX"
    df["Currency"] = "AUD"
    return df


async def scrape_earnings_us(end_date: datetime.date) -> pd.DataFrame:
    """Return US earnings announcements scheduled from today through ``end_date``.

    Args:
        end_date (datetime.date): Inclusive final announcement date. The date
            window uses ``America/New_York`` local calendar dates.

    Returns:
        A DataFrame with one row per earnings announcement and a contiguous,
        zero-based index. Returned rows contain no null fields. Columns, in order:

        - ``Announcement Date`` (str): Announcement date as ``YYYY-MM-DD``.
        - ``Exchange`` (str): Exchange code when known. ``"N/A"`` denotes an
          unrecognized security; a recognized security may have a blank exchange.
        - ``Ticker`` (str): Security code, such as ``"AAPL"``.
        - ``Company`` (str): Issuer name, with the ticker as fallback for absent or blank names.
        - ``Market Cap`` (int): Company market capitalization in whole USD.
        - ``EPS`` (float): Reported earnings per share in USD; may be negative.
        - ``EPS Forecast`` (float): Forecast earnings per share in USD; may be negative.
        - ``Revenue`` (int): Reported revenue in whole USD.
        - ``Revenue Forecast`` (int): Forecast revenue in whole USD.
        - ``Currency`` (str): Always ``"USD"``.

        Rows are grouped by ascending announcement date; order within a date
        is unspecified. No available announcements, or an end date before
        local today, produce an empty DataFrame retaining all columns.

    Raises:
        zoneinfo.ZoneInfoNotFoundError: If America/New_York timezone data is unavailable.
        ValueError: If earnings data is malformed, including missing/blank
            tickers or invalid/non-finite financial values.
        playwright.async_api.Error: If earnings retrieval cannot be started or finalized.

    Notes:
        Missing numeric fields and individual actual/forecast components default
        independently to zero: ``0.0`` for EPS fields and ``0`` for other numeric
        fields. A zero does not distinguish an unavailable value from an actual zero.
        Market capitalization and revenues use whole currency units; fractional
        units are discarded toward zero.

        Unavailable dates are omitted, so results may be incomplete. An empty
        result does not distinguish no announcements from unavailable data.
        A missing exchange identifier does not exclude an announcement.
    """
    url_template = "https://www.tipranks.com/calendars/earnings/{date}"
    tz = "America/New_York"
    df = await _scrape_earnings_from_tipranks(url_template, tz_name=tz, end_date=end_date)
    if df.empty:
        return df

    df["Currency"] = "USD"

    def _lookup_exchange(ticker: str) -> str:
        """Use the loaded US company's exchange; return ``"N/A"`` only when no company matches."""
        company = market.market_indices.revert_lookup_company("US", ticker)
        return company.extract_exchange_code()[0] if company else "N/A"

    df["Exchange"] = df["Ticker"].apply(_lookup_exchange)
    return df
