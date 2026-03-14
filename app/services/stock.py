from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import yfinance as yf
from ..models import finhub as models
from ..models.finhub import (
    SymbolInfo,
    StockQuote,
    SymbolOverview,
    HistoryPoint,
    UpcomingDividendEvent,
    UpcomingEarningsEvent,
)
from ..services import crawler as crawler_service
from ..utils import finhub as finhub_utils

allowed_quote_types = {"EQUITY", "ETF"}


def get_symbol_info_raw(symbol: str) -> dict[str, Any]:
    """
    Fetches detailed information about a ticker symbol.

    Args:
        symbol (str): The stock symbol to fetch information for.
    Returns:
        dict[str, Any]: A dictionary containing the raw information about the symbol.
    """
    ticker = yf.Ticker(symbol)
    info = ticker.info
    keys = list(info.keys())
    result = dict[str, Any]()
    for key in keys:
        # convert camelCase to snake_case
        snake_key = "".join(["_" + c.lower() if c.isupper() else c for c in key])
        result[snake_key] = info[key]
    return result


def get_symbol_info(symbol: str) -> SymbolInfo | None:
    """
    Fetches detailed information about a ticker symbol.

    Args:
        symbol (str): The stock symbol to fetch information for.
    Returns:
        SymbolInfo | None: A SymbolInfo object containing the information about the symbol, or None.
    """
    ticker = yf.Ticker(symbol)
    quote_type = ticker.info.get("quoteType")
    if quote_type in allowed_quote_types:
        return SymbolInfo(symbol=symbol, ticker=ticker)
    return None


def get_symbol_overview(symbol: str) -> SymbolOverview | None:
    """
    Fetches overview information about a ticker symbol.

    Args:
        symbol (str): The stock symbol to fetch information for.
    Returns:
        SymbolOverview | None: A SymbolOverview object containing the overview information about the symbol, or None.
    """
    ticker = yf.Ticker(symbol)
    quote_type = ticker.info.get("quoteType")
    if quote_type in allowed_quote_types:
        return SymbolOverview(ticker=ticker)
    return None


def get_stock_quotes(symbols: list[str]) -> dict[str, StockQuote]:
    """
    Fetches stock quotes for a list of ticker symbols.

    Args:
        symbols (list[str]): A list of stock symbols to fetch quotes for.
    Returns:
        dict[str, StockQuote]: A dictionary mapping each symbol to its corresponding StockQuote object.
    """
    tickers = yf.Tickers((" ".join(symbols)).upper())
    quotes = {}
    for symbol in symbols:
        symbol = symbol.upper().strip()
        ticker = tickers.tickers[symbol]
        quote_type = ticker.info.get("quoteType")
        if quote_type in allowed_quote_types:
            quotes[symbol] = StockQuote(ticker)
    return quotes


def get_stock_quote_at_date(symbol: str, date_str: str) -> HistoryPoint | None:
    """
    Fetches stock quote information for a given ticker symbol at a specific date.

    Args:
        symbol (str): The stock symbol to fetch information for.
        date_str (str): The date to fetch the quote for (format: YYYY-MM-DD).
    Returns:
        HistoryPoint | None: A HistoryPoint object containing the quote information for the symbol at the specified date, or None.
    """
    ticker = yf.Ticker(symbol)
    quote_type = ticker.info.get("quoteType")
    if quote_type in allowed_quote_types:
        try:
            start_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return None
        end_date = start_date + timedelta(days=1)
        start_date = start_date - timedelta(days=14)  # to account for weekends and holidays

        history = ticker.history(start=start_date, end=end_date, interval="1d", auto_adjust=False)
        if not history.empty:
            point = history.iloc[-1]
            return HistoryPoint(
                timestamp=point.name.timestamp(),
                timestamp_str=point.name.isoformat(sep=" ", timespec="seconds"),
                open=point["Open"],
                high=point["High"],
                low=point["Low"],
                close=point["Close"],
                volume=point["Volume"],
                dividends=point["Dividends"],
            )
    return None


# ----------------------------------------------------------------------#


def calc_end_date(tz: ZoneInfo):
    today = datetime.now(tz).date()
    end_date = today + timedelta(days=7)
    return end_date


async def get_upcoming_dividends_events(
    country: str, tz: ZoneInfo, default_vals: dict[str, Any] = None
) -> list[UpcomingDividendEvent]:
    """
    Check for upcoming dividend/distribution events (AU, US & VN only).

    Args:
        country (str): Country code to filter events by (e.g., 'AU', 'US', etc.).
        tz (ZoneInfo): Timezone to use for date calculations.
        default_vals (str): Optional, internal use
    Returns:
        list[UpcomingDividendEvent]: A list of upcoming dividend/distribution events
    """
    country = country.upper()
    end_date = calc_end_date(tz)
    raw_data = (
        await crawler_service.scrape_dividends_asx(end_date)
        if country == "AU" or country == "AUS" or country == "AUSTRALIA"
        else (
            await crawler_service.scrape_dividends_vn(end_date)
            if country == "VN" or country == "VIETNAM"
            else await crawler_service.scrape_dividends_us(end_date)
        )
    )
    if raw_data.empty:
        return []

    # optimize tokens:
    # - Removing rows where "Dividend Yield" too small (< 3.50%/AU, < 2.5%/US, < 10%/VN) or not in format of percentage
    # - Removing column "Url"
    # - If value in column "Dividend Amount" begins with "AU$"/"<AU$" or "$"/"<$", remove the prefix
    if "Dividend Amount" in raw_data.columns:
        raw_data["Dividend Amount"] = (
            raw_data["Dividend Amount"].astype(str).str.replace(r"^(AU\$|<AU\$|\$|<\$)", "", regex=True).astype(float)
        )
    if "Dividend Yield" in raw_data.columns:
        raw_data = raw_data[raw_data["Dividend Yield"].str.endswith("%")]
        if country == "AU" or country == "AUS" or country == "AUSTRALIA":
            raw_data = raw_data[raw_data["Dividend Yield"].str.rstrip("%").astype(float) >= 3.5]
        elif country == "US" or country == "UNITED STATES":
            raw_data = raw_data[raw_data["Dividend Yield"].str.rstrip("%").astype(float) >= 2.5]
        elif country == "VN" or country == "VIETNAM":
            raw_data = raw_data[raw_data["Dividend Yield"].str.rstrip("%").astype(float) >= 10]
    if "Url" in raw_data.columns:
        raw_data = raw_data.drop(columns=["Url"])

    # US market: remove rows where "Exchange Name" is not "NASDAQ" or "NYSE"
    if country == "US" or country == "USA" or country == "UNITED STATES":
        if "Exchange Name" in raw_data.columns:
            raw_data = raw_data[raw_data["Exchange Name"].isin(["NASDAQ", "NYSE"])]

    # VN market: copy Symbol column to Company Name
    if country == "VN" or country == "VIETNAM":
        if "Symbol" in raw_data.columns and "Company Name" not in raw_data.columns:
            raw_data["Company Name"] = raw_data["Symbol"]

    # final transformation of raw_data
    # - rename column Symbol to sym
    # - rename column Exchange Name to exchange
    # - rename column Company Name to corp
    # - rename column Ex-Dividend Date to date
    # - rename column Payment Date to pdate
    # - rename column Dividend Amount to amount
    # - rename column Dividend Yield to yield
    raw_data.rename(
        columns={
            "Symbol": "sym",
            "Exchange Name": "exchange",
            "Company Name": "corp",
            "Company": "corp",
            "Ex-Dividend Date": "date",
            "Payment Date": "pdate",
            "Dividend Amount": "amount",
            "Dividend Yield": "yield",
        },
        inplace=True,
    )
    # - add column event_category: "distribution" if company_name contains Trust, Fund, REIT, ETF, or Property. Else "dividend"
    raw_data["cat"] = raw_data["corp"].apply(
        lambda name: (
            "distribution"
            if any(kw in name.upper() for kw in ["TRUST", "FUND", "REIT", "ETF", "PROPERTY"])
            else "dividend"
        )
    )
    # - convert value of yield column from percent string to float. E.g. "3.5%" -> 0.035
    raw_data["yield"] = raw_data["yield"].str.rstrip("%").astype(float) / 100

    raw_data_json = raw_data.to_json(orient="records")
    events = models.parse_upcoming_dividend_events_from_json(raw_data_json, default_vals)
    for event in events:
        event.symbol = f"{event.exchange}:{event.symbol}"
        event.date = finhub_utils.yyyy_mm_dd_to_iso(event.date, tz=tz)
        event.timestamp = int(datetime.fromisoformat(event.date).timestamp())
        if event.payment_date:
            event.payment_date = finhub_utils.yyyy_mm_dd_to_iso(event.payment_date, tz=tz)
    return events


async def get_asx_upcoming_dividends_events() -> list[UpcomingDividendEvent]:
    """
    Check for upcoming dividend/distribution events for ASX.

    Returns:
        list[UpcomingDividendEvent]: A list of upcoming dividend/distribution events
    """
    country = "AU"
    tz = ZoneInfo("Australia/Sydney")
    default_vals = {
        "exchange": "ASX",
        "src": "ASX",
        "currency": "AUD",
        "status": "declared",
    }
    events = await get_upcoming_dividends_events(country, tz, default_vals)
    for event in events:
        event.link = f"https://www.asx.com.au/markets/company/{event.symbol.split(':')[-1]}"
    return events


async def get_us_upcoming_dividends_events() -> list[UpcomingDividendEvent]:
    """
    Check for upcoming dividend/distribution events for US market.

    Returns:
        list[UpcomingDividendEvent]: A list of upcoming dividend/distribution events
    """
    country = "US"
    tz = ZoneInfo("Australia/Sydney")
    default_vals = {
        "src": "StockAnalysis",
        "currency": "USD",
        "status": "declared",
    }
    events = await get_upcoming_dividends_events(country, tz, default_vals)
    for event in events:
        event.link = f"https://stockanalysis.com/stocks/{event.symbol.lower().split(':')[-1]}/dividend/"
    return events


async def get_vn_upcoming_dividends_events() -> list[UpcomingDividendEvent]:
    """
    Check for upcoming dividend/distribution events for VN market, using AI assistance.

    Returns:
        list[UpcomingDividendEvent]: A list of upcoming dividend/distribution events
    """
    country = "VN"
    tz = ZoneInfo("Asia/Ho_Chi_Minh")
    default_vals = {
        "cat": "dividend",
        "src": "VietStock",
        "currency": "VND",
        "status": "declared",
    }
    events = await get_upcoming_dividends_events(country, tz, default_vals)
    for event in events:
        event.link = f"https://finance.vietstock.vn/{event.symbol.split(':')[-1]}-thong-tin.htm"
    return events


async def get_upcoming_earnings_events(
    country: str, tz: ZoneInfo, default_vals: dict[str, Any] = None
) -> list[UpcomingEarningsEvent]:
    """
    Check for upcoming earnings events (AU  & US only).

    Args:
        country (str): Country code to filter events by (e.g., 'AU', 'US', etc.).
        tz (ZoneInfo): Timezone to use for date calculations.
        default_vals (str): Optional, internal use
    Returns:
        list[UpcomingEarningsEvent]: A list of upcoming earnings events
    """
    country = country.upper()
    end_date = calc_end_date(tz)
    raw_data = (
        await crawler_service.scrape_earnings_asx(end_date)
        if country == "AU" or country == "AUS" or country == "AUSTRALIA"
        else await crawler_service.scrape_earnings_us(end_date)
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

    raw_data_json = raw_data.to_json(orient="records")
    events = models.parse_upcoming_earnings_events_from_json(raw_data_json, default_vals)
    for event in events:
        event.symbol = f"{event.exchange}:{event.symbol}"
        event.date = finhub_utils.yyyy_mm_dd_to_iso(event.date, tz)
        event.timestamp = int(datetime.fromisoformat(event.date).timestamp())
    return events


async def get_asx_upcoming_earnings_events() -> list[UpcomingEarningsEvent]:
    """
    Check for upcoming earnings events for ASX.

    Returns:
        list[UpcomingEarningsEvent]: A list of upcoming earnings events
    """
    country = "AU"
    tz = ZoneInfo("Australia/Sydney")
    default_vals = {
        "exchange": "ASX",
        "src": "TipRanks",
        "status": "estimated",
        "report_period": "N/A",
    }
    events = await get_upcoming_earnings_events(country, tz, default_vals)
    for event in events:
        event.link = f"https://www.tipranks.com/stocks/au:{event.symbol.lower().split(':')[-1]}/earnings"
    return events


async def get_us_upcoming_earnings_events() -> list[UpcomingEarningsEvent]:
    """
    Check for upcoming earnings events for US market.

    Returns:
        list[UpcomingEarningsEvent]: A list of upcoming earnings events
    """
    country = "US"
    tz = ZoneInfo("America/New_York")
    default_vals = {
        "src": "TipRanks",
        "status": "estimated",
        "report_period": "N/A",
    }
    events = await get_upcoming_earnings_events(country, tz, default_vals)
    for event in events:
        event.link = f"https://www.tipranks.com/stocks/{event.symbol.lower().split(':')[-1]}/earnings"
    return events
