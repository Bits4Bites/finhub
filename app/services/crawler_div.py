import asyncio
import datetime
import math
import random
import zoneinfo

import pandas as pd

from . import crawler_core, market

_DIVIDEND_COLUMNS = [
    "Ticker",
    "Company",
    "Ex-Div Date",
    "Payment Date",
    "Div Amount",
    "Div Yield",
    "Market Cap",
    "Exchange",
    "Currency",
]
_DIVIDEND_NUMERIC_DEFAULTS = {"Div Amount": 0.0, "Div Yield": 0.0, "Market Cap": 0}
_MISSING_NUMERIC_MARKERS = {"", "N/A", "NA", "NAN", "-"}
_NO_DIVIDENDS_MESSAGE = "Currently there are no dividends available for this date."


def _empty_dividend_frame() -> pd.DataFrame:
    """Return an empty frame with the shared dividend columns in order."""
    return pd.DataFrame(columns=_DIVIDEND_COLUMNS)


def _canonicalize_dividend_frame(data: pd.DataFrame) -> pd.DataFrame:
    """Copy rows into canonical columns, default missing numerics to zero, and retain other nulls."""
    if data.empty:
        return _empty_dividend_frame()

    result = data.copy()
    for column in _DIVIDEND_COLUMNS:
        if column not in result.columns:
            result[column] = _DIVIDEND_NUMERIC_DEFAULTS.get(column, pd.NA)
    for column, default in _DIVIDEND_NUMERIC_DEFAULTS.items():
        values = result[column]
        if pd.api.types.is_string_dtype(values.dtype):
            values = values.astype(object)
        result[column] = values.fillna(default)
    return result.loc[:, _DIVIDEND_COLUMNS].reset_index(drop=True)


def _validate_required_dividend_fields(
    data: pd.DataFrame,
    required_columns: set[str],
    *,
    nullable_columns: set[str] | None = None,
) -> None:
    """Reject missing columns and blank/null required values, except for explicitly nullable fields."""
    missing_columns = required_columns.difference(data.columns)
    if missing_columns:
        raise ValueError(f"Dividend table is missing columns: {sorted(missing_columns)}")

    missing_values = {
        column
        for column in required_columns.difference(nullable_columns or set())
        if data[column].isna().any() or data[column].astype(str).str.strip().eq("").any()
    }
    if missing_values:
        raise ValueError(f"Dividend table has missing values in required columns: {sorted(missing_values)}")


def _parse_percentage(value) -> float:
    """Convert percentages to fractions, preserve bare fractions, and default missing values to zero."""
    if pd.isna(value):
        return 0.0
    text = str(value).strip()
    if text.upper() in _MISSING_NUMERIC_MARKERS:
        return 0.0
    percentage = float(text[:-1].replace(",", "")) / 100 if text.endswith("%") else float(text.replace(",", ""))
    return 0.0 if math.isnan(percentage) else percentage


def _parse_money_amount(value) -> float:
    """Parse optional currency prefixes and commas, defaulting missing amounts to zero."""
    if pd.isna(value):
        return 0.0
    text = str(value).strip().replace(",", "")
    for prefix in ("AU$", "US$", "$"):
        if text.upper().startswith(prefix):
            text = text[len(prefix) :].strip()
            break
    if text.upper() in _MISSING_NUMERIC_MARKERS:
        return 0.0
    try:
        amount = float(text)
        if not math.isfinite(amount):
            raise ValueError("amount must be finite")
        return amount
    except ValueError as exc:
        raise ValueError(f"invalid amount: {value!r}") from exc


def _parse_market_cap(value) -> int:
    """Expand K/M/B/T market-cap suffixes, defaulting missing values to zero."""
    if pd.isna(value):
        return 0
    text = str(value).replace("$", "").replace(",", "").strip()
    if text.upper() in _MISSING_NUMERIC_MARKERS:
        return 0

    multiplier = 1
    if text[-1].upper() in {"T", "B", "M", "K"}:
        multiplier = {"T": 10**12, "B": 10**9, "M": 10**6, "K": 10**3}[text[-1].upper()]
        text = text[:-1]
    try:
        return int(float(text) * multiplier)
    except ValueError as exc:
        raise ValueError(f"invalid market capitalization: {value!r}") from exc


def _tipranks_payment_date(value, ex_div_date: str) -> str | None:
    """Resolve relative payment dates against the ex-dividend date, with "Next Month" meaning 30 days.

    Missing or unrecognized absolute dates return null; malformed relative offsets raise ValueError.
    """
    if pd.isna(value):
        return None
    text = str(value).strip()
    if not text or text.upper() in {"N/A", "NA", "-"}:
        return None
    if text == "Next Month":
        text = "In 30 Days"
    if text.startswith("In "):
        try:
            days = int(text.split()[1])
        except (IndexError, ValueError) as exc:
            raise ValueError(f"invalid relative payment date: {value!r}") from exc
        return (datetime.datetime.strptime(ex_div_date, "%Y-%m-%d") + datetime.timedelta(days=days)).date().isoformat()
    try:
        return datetime.date.fromisoformat(text).isoformat()
    except ValueError:
        return None


async def _scrape_dividends_from_tipranks(
    url_template: str,
    *,
    tz_name: str = "UTC",
    tz_info: zoneinfo.ZoneInfo | None = None,
    end_date: datetime.date,
) -> pd.DataFrame:
    """Collect TipRanks dividends from local today through the inclusive end date.

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
        cache_ttl=60 * 60,
    )
    frames = []
    rename_map = {
        "Name": "Ticker",
        "Dividend Yield": "Div Yield",
        "Dividend Amount": "Div Amount",
    }
    for index, page_content in enumerate(page_content_list):
        if page_content is None:
            continue
        page_df = crawler_core.extract_data_table_from_html(page_content)
        if page_df.empty:
            continue
        page_df = page_df[page_df.iloc[:, 0] != _NO_DIVIDENDS_MESSAGE].copy()
        if page_df.empty:
            continue
        page_df = page_df.rename(columns=rename_map)
        _validate_required_dividend_fields(page_df, {"Ticker", "Div Amount"}, nullable_columns={"Div Amount"})
        page_df["Ex-Div Date"] = dates[index]
        if "Payment Date" in page_df.columns:
            page_df["Payment Date"] = page_df["Payment Date"].apply(
                lambda value: _tipranks_payment_date(value, dates[index])
            )
        frames.append(page_df)

    if not frames:
        return _empty_dividend_frame()

    df = pd.concat(frames, ignore_index=True)
    cols_to_remove = ["Analyst Consensus", "Smart Score", "Payout Ratio", "Follow"]
    df = df.drop(columns=cols_to_remove, errors="ignore")
    df = _canonicalize_dividend_frame(df)
    missing_company = df["Company"].isna() | df["Company"].astype(str).str.strip().eq("")
    df["Company"] = df["Company"].mask(missing_company, df["Ticker"])
    df["Div Yield"] = df["Div Yield"].apply(_parse_percentage)
    df["Div Amount"] = df["Div Amount"].apply(_parse_money_amount)
    df["Market Cap"] = df["Market Cap"].apply(_parse_market_cap)
    return df


async def scrape_dividends_asx(end_date: datetime.date) -> pd.DataFrame:
    """Return announced ASX dividends from today through ``end_date``.

    Args:
        end_date (datetime.date): Inclusive final ex-dividend date, interpreted
            in Australia/Sydney time.

    Returns:
        A DataFrame with one row per dividend announcement and a zero-based
        index. Columns, in order:

        - ``Ticker`` (str): Security code, such as ``"CBA"``.
        - ``Company`` (str): Issuer name, or the ticker when no name is available.
        - ``Ex-Div Date`` (str): Ex-dividend date as ``YYYY-MM-DD``.
        - ``Payment Date`` (str or null): Expected payment date as ``YYYY-MM-DD``,
          when available.
        - ``Div Amount`` (number): Cash dividend per share in AUD.
        - ``Div Yield`` (number): Dividend yield as a decimal fraction;
          ``0.04`` means 4%.
        - ``Market Cap`` (number): Company market capitalization in AUD.
        - ``Exchange`` (str): Always ``"ASX"``.
        - ``Currency`` (str): Always ``"AUD"``.

        Rows are grouped by ascending ex-dividend date; order within a date is
        unspecified. No available announcements, or an end date before today,
        produce an empty DataFrame retaining all columns.

    Raises:
        zoneinfo.ZoneInfoNotFoundError: If Australia/Sydney timezone data is
            unavailable.
        ValueError: If required announcement fields are missing or an amount,
            yield, market capitalization, or relative payment date is malformed.
        playwright.async_api.Error: If the retrieval session cannot be started
            or closed.

    Notes:
        Source pages may be cached for up to one hour.
        Missing amounts and yields use ``0.0``; missing market capitalization
        uses ``0``. Required source columns must still be present.
        Null denotes a pandas missing value, not a particular scalar or dtype.
        Unavailable dates are omitted, so results may be incomplete rather than
        raising an exception for each failed date.
    """
    url_template = "https://www.tipranks.com/calendars/dividends/{date}/australia"
    tz = "Australia/Sydney"
    df = await _scrape_dividends_from_tipranks(url_template, tz_name=tz, end_date=end_date)
    if df.empty:
        return df

    df["Exchange"] = "ASX"
    df["Currency"] = "AUD"
    return df


async def scrape_dividends_us(end_date: datetime.date) -> pd.DataFrame:
    """Return announced US dividends from today through ``end_date``.

    Args:
        end_date (datetime.date): Inclusive final ex-dividend date, interpreted
            in America/New_York time.

    Returns:
        A DataFrame with one row per dividend announcement and a zero-based
        index. Columns, in order:

        - ``Ticker`` (str): Security code, such as ``"AAPL"``.
        - ``Company`` (str): Issuer name, or the ticker when no name is available.
        - ``Ex-Div Date`` (str): Ex-dividend date as ``YYYY-MM-DD``.
        - ``Payment Date`` (str or null): Expected payment date as ``YYYY-MM-DD``,
          when available.
        - ``Div Amount`` (number): Cash dividend per share in USD.
        - ``Div Yield`` (number): Dividend yield as a decimal fraction;
          ``0.04`` means 4%.
        - ``Market Cap`` (number): Company market capitalization in USD.
        - ``Exchange`` (str): Exchange code when identified, or ``"N/A"``.
        - ``Currency`` (str): Always ``"USD"``.

        Rows are grouped by ascending ex-dividend date; order within a date is
        unspecified. No available announcements, or an end date before today,
        produce an empty DataFrame retaining all columns.

    Raises:
        zoneinfo.ZoneInfoNotFoundError: If America/New_York timezone data is
            unavailable.
        ValueError: If required announcement fields are missing or an amount,
            yield, market capitalization, or relative payment date is malformed.
        playwright.async_api.Error: If the retrieval session cannot be started
            or closed.

    Notes:
        Source pages may be cached for up to one hour.
        Missing amounts and yields use ``0.0``; missing market capitalization
        uses ``0``. Required source columns must still be present.
        Null denotes a pandas missing value, not a particular scalar or dtype.
        Unavailable dates are omitted, so results may be incomplete rather than
        raising an exception for each failed date. An unidentified exchange does
        not exclude the announcement.
    """
    url_template = "https://www.tipranks.com/calendars/dividends/{date}"
    tz = "America/New_York"
    df = await _scrape_dividends_from_tipranks(url_template, tz_name=tz, end_date=end_date)
    if df.empty:
        return df

    df["Currency"] = "USD"

    def _lookup_exchange(ticker: str) -> str:
        """Resolve the exchange from loaded US constituents, or return "N/A"."""
        company = market.market_indices.revert_lookup_company("US", ticker)
        return company.extract_exchange_code()[0] if company else "N/A"

    df["Exchange"] = df["Ticker"].apply(_lookup_exchange)
    return df


async def _wait_for_vietstock_page_render_after_load_func(_page):
    """Wait one to two seconds for VietStock's event table to finish rendering."""
    delay_seconds = random.uniform(1.00, 2.00)
    await asyncio.sleep(delay_seconds)


async def _scrape_cash_dividends_vn_vietstock(end_date: datetime.date) -> pd.DataFrame:
    """Collect inclusive VietStock cash-dividend pages using VND 10,000 par value for amounts.

    An empty or unavailable page ends collection but preserves earlier rows.
    """
    tz_name = "Asia/Ho_Chi_Minh"
    start_date = datetime.datetime.now(zoneinfo.ZoneInfo(tz_name)).date()
    if start_date > end_date:
        return _empty_dividend_frame()

    url_template = "https://finance.vietstock.vn/lich-su-kien.htm?from={s_date}&to={e_date}&page={page}&tab=1&group=13"
    rename_map = {
        "Mã CK": "Ticker",
        "Sàn": "Exchange",
        "Ngày GDKHQ▼": "Ex-Div Date",
        "Ngày thực hiện": "Payment Date",
        "Tỷ lệ": "Div Yield",
    }
    frames = []
    page = 1
    while True:
        target_url = url_template.format(
            s_date=start_date.strftime("%Y-%m-%d"),
            e_date=end_date.strftime("%Y-%m-%d"),
            page=page,
        )
        df = await crawler_core.scrape_data_table_playwright(
            target_url,
            table_attr_filter={"id": "event-content"},
            after_load_func_async=_wait_for_vietstock_page_render_after_load_func,
            cache_ttl=60 * 60,
        )
        if df.empty or len(df.columns) < 2:
            break

        df = df.rename(columns=rename_map)
        _validate_required_dividend_fields(
            df,
            {"Ticker", "Exchange", "Ex-Div Date", "Div Yield"},
            nullable_columns={"Div Yield"},
        )
        frames.append(df)

        # delay randomly a few seconds to avoid overwhelming the server
        delay_seconds = random.uniform(1.00, 3.00)
        await asyncio.sleep(delay_seconds)

        page += 1

    if not frames:
        return _empty_dividend_frame()

    final_df = pd.concat(frames, ignore_index=True)
    final_df = final_df.drop(columns=["STT", "Nội dung sự kiện", "Ngày ĐKCC"], errors="ignore")
    final_df["Exchange"] = final_df["Exchange"].astype(str).str.upper()
    ex_div_dates = pd.to_datetime(final_df["Ex-Div Date"], format="%d/%m/%Y", errors="raise")
    if ex_div_dates.isna().any():
        raise ValueError("invalid ex-dividend date")
    final_df["Ex-Div Date"] = ex_div_dates.dt.strftime("%Y-%m-%d")
    if "Payment Date" in final_df.columns:
        payment_dates = pd.to_datetime(final_df["Payment Date"], format="%d/%m/%Y", errors="coerce")
        final_df["Payment Date"] = payment_dates.dt.strftime("%Y-%m-%d").where(payment_dates.notna(), None)

    final_df["Div Yield"] = final_df["Div Yield"].apply(_parse_percentage)
    final_df["Company"] = final_df["Ticker"]
    final_df["Div Amount"] = final_df["Div Yield"] * 10000
    final_df["Market Cap"] = 0
    final_df["Currency"] = "VND"

    return _canonicalize_dividend_frame(final_df)


async def scrape_dividends_vn(end_date: datetime.date) -> pd.DataFrame:
    """Return announced Vietnamese cash dividends from today through ``end_date``.

    Args:
        end_date (datetime.date): Inclusive final ex-dividend date, interpreted
            in Asia/Ho_Chi_Minh time.

    Returns:
        A DataFrame with one row per cash-dividend announcement and a zero-based
        index. Columns, in order:

        - ``Ticker`` (str): Security code, such as ``"VNM"``.
        - ``Company`` (str): The ticker, rather than a separate issuer name.
        - ``Ex-Div Date`` (str): Ex-dividend date as ``YYYY-MM-DD``.
        - ``Payment Date`` (str or null): Payment date as ``YYYY-MM-DD``, when
          known and valid.
        - ``Div Amount`` (number): Cash dividend per share in VND, assuming a
          VND 10,000 nominal share value; ``0.0`` when the rate is missing.
        - ``Div Yield`` (number): Cash-dividend rate relative to nominal
          share value, not market price; ``0.15`` means 15%.
        - ``Market Cap`` (number): Always ``0`` because it is not available.
        - ``Exchange`` (str): Uppercase market code, such as ``"HOSE"``.
        - ``Currency`` (str): Always ``"VND"``.

        Row order is unspecified. No available announcements, or an end date
        before today, produce an empty DataFrame retaining all columns.

    Raises:
        zoneinfo.ZoneInfoNotFoundError: If Asia/Ho_Chi_Minh timezone data is
            unavailable.
        ValueError: If required announcement fields are missing or an
            ex-dividend date or dividend rate is malformed.

    Notes:
        Source pages may be cached for up to one hour.
        Missing amounts and rates use ``0.0``; missing market capitalization
        uses ``0``. Required source columns must still be present.
        Null denotes a pandas missing value, not a particular scalar or dtype.
        Retrieval failures can leave partial or empty results rather than
        raising an exception.
    """
    return await _scrape_cash_dividends_vn_vietstock(end_date)
