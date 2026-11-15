import asyncio
import datetime
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
_NO_DIVIDENDS_MESSAGE = "Currently there are no dividends available for this date."


def _empty_dividend_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=_DIVIDEND_COLUMNS)


def _canonicalize_dividend_frame(data: pd.DataFrame) -> pd.DataFrame:
    if data.empty:
        return _empty_dividend_frame()

    result = data.copy()
    for column in _DIVIDEND_COLUMNS:
        if column not in result.columns:
            result[column] = pd.NA
    return result.loc[:, _DIVIDEND_COLUMNS].reset_index(drop=True)


def _parse_percentage(value) -> float | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    if not text or text.upper() in {"N/A", "NA", "-"}:
        return None
    if text.endswith("%"):
        return float(text[:-1].replace(",", "")) / 100
    return float(text.replace(",", ""))


def _parse_money_amount(value) -> float:
    text = str(value).strip().replace(",", "")
    for prefix in ("AU$", "US$", "$"):
        if text.upper().startswith(prefix):
            text = text[len(prefix) :]
            break
    try:
        return float(text)
    except ValueError as exc:
        raise ValueError(f"invalid dividend amount: {value!r}") from exc


def _parse_market_cap(value) -> int | None:
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


def _tipranks_payment_date(value, ex_div_date: str) -> str | None:
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
    """Collect and normalize TipRanks dividend rows through ``end_date``."""
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
        delay_between_requests=1.0,
    )
    frames = []
    for index, page_content in enumerate(page_content_list):
        if page_content is None:
            continue
        page_df = crawler_core.extract_data_table_from_html(page_content)
        if page_df.empty:
            continue
        page_df = page_df[page_df.iloc[:, 0] != _NO_DIVIDENDS_MESSAGE].copy()
        if page_df.empty:
            continue
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
    df = df.rename(columns={"Name": "Ticker"})
    df = df.rename(columns={"Dividend Yield": "Div Yield"})
    df = df.rename(columns={"Dividend Amount": "Div Amount"})

    required_columns = {"Ticker", "Div Amount"}
    missing_columns = required_columns.difference(df.columns)
    if missing_columns:
        raise ValueError(f"TipRanks dividend table is missing columns: {sorted(missing_columns)}")

    if "Company" not in df.columns:
        df["Company"] = df["Ticker"]
    if "Payment Date" not in df.columns:
        df["Payment Date"] = pd.NA
    if "Div Yield" not in df.columns:
        df["Div Yield"] = pd.NA
    if "Market Cap" not in df.columns:
        df["Market Cap"] = pd.NA

    df["Div Yield"] = df["Div Yield"].apply(_parse_percentage)
    df["Div Amount"] = df["Div Amount"].apply(_parse_money_amount)
    df["Market Cap"] = df["Market Cap"].apply(_parse_market_cap)
    return _canonicalize_dividend_frame(df)


async def scrape_dividends_asx(end_date: datetime.date) -> pd.DataFrame:
    """Return announced ASX dividends from today through ``end_date``.

    Args:
        end_date: Inclusive final calendar date in Sydney time.

    Returns:
        A DataFrame with the canonical columns ``Ticker``, ``Company``,
        ``Ex-Div Date``, ``Payment Date``, ``Div Amount``, ``Div Yield``,
        ``Market Cap``, ``Exchange``, and ``Currency``. Dates use
        ``YYYY-MM-DD``; yields are decimal fractions; numeric amounts are in AUD.
        No announcements, failed pages, or an end date before today produce an
        empty DataFrame with those columns.

    Raises:
        ZoneInfoNotFoundError: If the configured Sydney timezone is unavailable.
        ValueError: If a returned source row cannot be normalized to the
            canonical contract.

    Notes:
        ``Payment Date``, ``Div Yield``, and ``Market Cap`` may contain null
        values when TipRanks does not report them.
    """
    url_template = "https://www.tipranks.com/calendars/dividends/{date}/australia"
    tz = "Australia/Sydney"
    df = await _scrape_dividends_from_tipranks(url_template, tz_name=tz, end_date=end_date)
    df["Exchange"] = "ASX"
    df["Currency"] = "AUD"
    return _canonicalize_dividend_frame(df)


async def scrape_dividends_us(end_date: datetime.date) -> pd.DataFrame:
    """Return announced US dividends from today through ``end_date``.

    Args:
        end_date: Inclusive final calendar date in New York time.

    Returns:
        A DataFrame with the same canonical columns and value formats as
        :func:`scrape_dividends_asx`, with USD amounts. Tickers not found in the
        loaded US market-index data have exchange ``"N/A"`` so event callers can
        discard them. No announcements, failed pages, or an end date before
        today produce a canonical empty DataFrame.

    Raises:
        ZoneInfoNotFoundError: If the configured New York timezone is
            unavailable.
        ValueError: If a returned source row cannot be normalized to the
            canonical contract.

    Notes:
        Exchange identification is limited to companies in the application's
        loaded US index datasets.
    """
    url_template = "https://www.tipranks.com/calendars/dividends/{date}"
    tz = "America/New_York"
    df = await _scrape_dividends_from_tipranks(url_template, tz_name=tz, end_date=end_date)
    df["Currency"] = "USD"

    def _lookup_exchange(ticker: str) -> str:
        company = market.market_indices.revert_lookup_company("US", ticker)
        return company.extract_exchange_code()[0] if company else "N/A"

    df["Exchange"] = df["Ticker"].apply(_lookup_exchange)
    return _canonicalize_dividend_frame(df)


async def _wait_for_vietstock_page_render_after_load_func(*args, **kwargs):
    delay_seconds = random.uniform(1.00, 2.00)
    await asyncio.sleep(delay_seconds)


async def _scrape_cash_dividends_vn_vietstock(start_date: datetime.date, end_date: datetime.date) -> pd.DataFrame:
    """Collect and normalize VietStock cash-dividend rows for a date range."""
    if start_date > end_date:
        return _empty_dividend_frame()

    url_template = "https://finance.vietstock.vn/lich-su-kien.htm?from={s_date}&to={e_date}&page={page}&tab=1&group=13"
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
        )
        if df.empty or len(df.columns) < 2:
            break

        frames.append(df)

        # delay randomly a few seconds to avoid overwhelming the server
        delay_seconds = random.uniform(1.00, 3.00)
        await asyncio.sleep(delay_seconds)

        page += 1

    if not frames:
        return _empty_dividend_frame()

    final_df = pd.concat(frames, ignore_index=True)
    final_df = final_df.drop(columns=["STT", "Nội dung sự kiện", "Ngày ĐKCC"], errors="ignore")
    rename_map = {
        "Mã CK": "Ticker",
        "Sàn": "Exchange",
        "Ngày GDKHQ▼": "Ex-Div Date",
        "Ngày thực hiện": "Payment Date",
        "Tỷ lệ": "Div Yield",
    }
    final_df = final_df.rename(columns=rename_map)

    required_columns = {"Ticker", "Exchange", "Ex-Div Date", "Div Yield"}
    missing_columns = required_columns.difference(final_df.columns)
    if missing_columns:
        raise ValueError(f"VietStock dividend table is missing columns: {sorted(missing_columns)}")

    final_df["Exchange"] = final_df["Exchange"].astype(str).str.upper()
    final_df["Ex-Div Date"] = pd.to_datetime(final_df["Ex-Div Date"], format="%d/%m/%Y", errors="raise").dt.strftime(
        "%Y-%m-%d"
    )
    if "Payment Date" in final_df.columns:
        payment_dates = pd.to_datetime(final_df["Payment Date"], format="%d/%m/%Y", errors="coerce")
        final_df["Payment Date"] = payment_dates.dt.strftime("%Y-%m-%d").where(payment_dates.notna(), None)
    else:
        final_df["Payment Date"] = pd.NA

    final_df["Div Yield"] = final_df["Div Yield"].apply(_parse_percentage)
    final_df["Company"] = final_df["Ticker"]
    final_df["Div Amount"] = final_df["Div Yield"] * 10000
    final_df["Market Cap"] = pd.NA
    final_df["Currency"] = "VND"

    return _canonicalize_dividend_frame(final_df)


async def scrape_dividends_vn(end_date: datetime.date) -> pd.DataFrame:
    """Return announced Vietnamese cash dividends through ``end_date``.

    Args:
        end_date: Inclusive final calendar date in Ho Chi Minh City time.

    Returns:
        A DataFrame with the same canonical columns as the ASX and US dividend
        crawlers. Dates use ``YYYY-MM-DD``; yields are decimal fractions;
        amounts are VND. No rows, failed pages, or an end date before the
        lookback window produce a canonical empty DataFrame.

    Raises:
        ZoneInfoNotFoundError: If the configured Ho Chi Minh City timezone is
            unavailable.
        ValueError: If a returned VietStock row has an invalid required date,
            yield, or source schema.

    Notes:
        VietStock group 13 supplies cash dividends only. ``Div Amount`` is
        derived from the reported percentage using the standard VND 10,000 par
        value, and ``Company`` falls back to the ticker because this calendar
        does not provide issuer names. The query begins two working days before
        today so recently announced events remain visible.
    """
    tz_name = "Asia/Ho_Chi_Minh"
    start_date = datetime.datetime.now(zoneinfo.ZoneInfo(tz_name)).date()
    # go back 2 working days
    for _ in range(2):
        start_date -= datetime.timedelta(days=1)
        # if weekend, go back to the previous Friday
        if start_date.weekday() >= 5:  # Saturday or Sunday
            start_date -= datetime.timedelta(days=start_date.weekday() - 4)

    return await _scrape_cash_dividends_vn_vietstock(start_date, end_date)
