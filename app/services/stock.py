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
        symbol (str): The stock symbol to fetch information for, accepting YF format (e.g. ABC.AX) or EXCHANGE:CODE (e.g. NASDAQ:XYZ).

    Returns:
        SymbolInfo | None: A SymbolInfo object containing the information about the symbol, or None.
    """
    yf_symbol = finhub_utils.to_yf_ticker(symbol)
    ticker = yf.Ticker(yf_symbol)
    quote_type = ticker.info.get("quoteType")
    if quote_type in allowed_quote_types:
        return SymbolInfo(ticker)
    return None


def get_symbol_overview(symbol: str) -> SymbolOverview | None:
    """
    Fetches overview information about a ticker symbol.

    Args:
        symbol (str): The stock symbol to fetch information for, accepting YF format (e.g. ABC.AX) or EXCHANGE:CODE (e.g. NASDAQ:XYZ).

    Returns:
        SymbolOverview | None: A SymbolOverview object containing the overview information about the symbol, or None.
    """
    yf_symbol = finhub_utils.to_yf_ticker(symbol)
    ticker = yf.Ticker(yf_symbol)
    quote_type = ticker.info.get("quoteType")
    if quote_type in allowed_quote_types:
        return SymbolOverview(ticker)
    return None


def get_stock_quotes(symbols: list[str]) -> dict[str, StockQuote]:
    """
    Fetches stock quotes for a list of ticker symbols.

    Args:
        symbols (list[str]): A list of stock symbols to fetch quotes for, accepting YF format (e.g. ABC.AX) or EXCHANGE:CODE (e.g. NASDAQ:XYZ).

    Returns:
        dict[str, StockQuote]: A dictionary mapping each symbol to its corresponding StockQuote object.
    """
    yf_symbols = [finhub_utils.to_yf_ticker(s) for s in symbols]
    tickers = yf.Tickers(" ".join(yf_symbols))
    quotes = {}
    for i in range(0, len(symbols)):
        yf_symbol = yf_symbols[i]
        if yf_symbol in tickers.tickers:
            ticker = tickers.tickers[yf_symbol]
            quote_type = ticker.info.get("quoteType") if ticker.info.get("quoteType") is not None else "NONE"
            if quote_type in allowed_quote_types:
                symbol = symbols[i]
                quotes[symbol] = StockQuote(ticker)
    return quotes


def get_stock_quote_at_date(symbol: str, date_str: str) -> HistoryPoint | None:
    """
    Fetches stock quote information for a given ticker symbol at a specific date.

    Args:
        symbol (str): The stock symbol to fetch information for, accepting YF format (e.g. ABC.AX) or EXCHANGE:CODE (e.g. NASDAQ:XYZ).
        date_str (str): The date to fetch the quote for (format: YYYY-MM-DD).

    Returns:
        HistoryPoint | None: A HistoryPoint object containing the quote information for the symbol at the specified date, or None.
    """
    yf_symbol = finhub_utils.to_yf_ticker(symbol)
    ticker = yf.Ticker(yf_symbol)
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


def calc_end_date_to_fetch_events(*, event_type: str, tz: ZoneInfo, index: str = ""):
    today = datetime.now(tz).date()
    if index:  # if index is provided to filter events, we look further into the future to capture more relevant events
        if "EARNINGS" in event_type.upper():
            end_date = today + timedelta(days=10)
        else:
            end_date = today + timedelta(days=14)
    else:  # if no index filter is provided, we can look at a shorter time window for more immediate events
        end_date = today + timedelta(days=7)
    return end_date


async def get_upcoming_dividends_events(
    country: str,
    tz: ZoneInfo,
    *,
    default_vals: dict[str, Any] = None,
    index: str = "",
) -> list[UpcomingDividendEvent]:
    """
    Check for upcoming dividend/distribution events (AU, US & VN only).

    Args:
        country (str): Country code to filter events by (e.g., 'AU', 'US', etc.).
        tz (ZoneInfo): Timezone to use for date calculations.
        default_vals (str, optional): internal use
        index (str, optional): internal use

    Returns:
        list[UpcomingDividendEvent]: A list of upcoming dividend/distribution events
    """
    country = country.upper()
    end_date = calc_end_date_to_fetch_events(event_type="DIVIDEND", tz=tz, index=index)
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
    # - Removing rows where "Dividend Yield" too small (< 2.0%/AU, < 0.5%/US, < 10%/VN) or not in format of percentage
    # - Removing column "Url"
    # - If value in column "Dividend Amount" begins with "AU$"/"<AU$" or "$"/"<$" or "<" remove the prefix
    if "Dividend Amount" in raw_data.columns:
        raw_data["Dividend Amount"] = (
            raw_data["Dividend Amount"].astype(str).str.replace(r"^(AU\$|<AU\$|\$|<\$|<)", "", regex=True).astype(float)
        )
    if "Dividend Yield" in raw_data.columns:
        raw_data = raw_data[raw_data["Dividend Yield"].str.endswith("%")]
        if country == "AU" or country == "AUS" or country == "AUSTRALIA":
            raw_data = raw_data[
                raw_data["Dividend Yield"].str.replace(r"[^\d\.]+", "", regex=True).astype(float) >= 2.0
            ]
        elif country == "US" or country == "USA" or country == "UNITED STATES":
            raw_data = raw_data[
                raw_data["Dividend Yield"].str.replace(r"[^\d\.]+", "", regex=True).astype(float) >= 0.5
            ]
        elif country == "VN" or country == "VIETNAM":
            raw_data = raw_data[raw_data["Dividend Yield"].str.replace(r"[^\d\.]+", "", regex=True).astype(float) >= 10]
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


async def get_asx_upcoming_dividends_events(index: str = "") -> list[UpcomingDividendEvent]:
    """
    Check for upcoming dividend/distribution events for ASX.

    Args:
        index (str, optional): ASX index to filter stocks (e.g. ASX20, ASX50, ASX100, ASX200 and ASX300)

    Returns:
        list[UpcomingDividendEvent]: A list of upcoming dividend/distribution events
    """
    asx_indices = ["ASX20", "ASX50", "ASX100", "ASX200", "ASX300"]
    index = index.upper()
    if index and index not in asx_indices:
        return []

    country = "AU"
    tz = ZoneInfo("Australia/Sydney")
    default_vals = {
        "exchange": "ASX",
        "src": "ASX",
        "currency": "AUD",
        "status": "declared",
    }
    events = await get_upcoming_dividends_events(country, tz, default_vals=default_vals, index=index)
    if index:
        events = [e for e in events if finhub_utils.is_in_index(e.symbol, index)]

    for event in events:
        event.link = f"https://www.asx.com.au/markets/company/{event.symbol.split(':')[-1]}"
    return events


async def get_us_upcoming_dividends_events(index: str = "") -> list[UpcomingDividendEvent]:
    """
    Check for upcoming dividend/distribution events for US market.

    Args:
        index (str, optional): index to filter stocks (e.g. NASDAQ100, SP500, SP400 and SP600)

    Returns:
        list[UpcomingDividendEvent]: A list of upcoming dividend/distribution events
    """
    us_indices = ["NASDAQ100", "SP500", "SP400", "SP600"]
    index = index.upper()
    if index and index not in us_indices:
        return []

    country = "US"
    tz = ZoneInfo("America/New_York")
    default_vals = {
        "src": "StockAnalysis",
        "currency": "USD",
        "status": "declared",
    }
    events = await get_upcoming_dividends_events(country, tz, default_vals=default_vals, index=index)
    if index:
        events = [e for e in events if finhub_utils.is_in_index(e.symbol, index)]

    for event in events:
        event.link = f"https://stockanalysis.com/stocks/{event.symbol.lower().split(':')[-1]}/dividend/"
    return events


async def get_vn_upcoming_dividends_events(index: str = "") -> list[UpcomingDividendEvent]:
    """
    Check for upcoming dividend/distribution events for VN market, using AI assistance.

    Args:
        index (str, optional): index to filter stocks (e.g. VN30, VN100 and HNX30)

    Returns:
        list[UpcomingDividendEvent]: A list of upcoming dividend/distribution events
    """
    vn_indices = ["VN30", "VN100", "HNX30"]
    index = index.upper()
    if index and index not in vn_indices:
        return []

    country = "VN"
    tz = ZoneInfo("Asia/Ho_Chi_Minh")
    default_vals = {
        "cat": "dividend",
        "src": "VietStock",
        "currency": "VND",
        "status": "declared",
    }
    events = await get_upcoming_dividends_events(country, tz, default_vals=default_vals, index=index)
    if index:
        events = [e for e in events if finhub_utils.is_in_index(e.symbol, index)]

    for event in events:
        event.link = f"https://finance.vietstock.vn/{event.symbol.split(':')[-1]}-thong-tin.htm"
    return events


async def get_upcoming_earnings_events(
    country: str, tz: ZoneInfo, *, default_vals: dict[str, Any] = None, index: str = ""
) -> list[UpcomingEarningsEvent]:
    """
    Check for upcoming earnings events (AU  & US only).

    Args:
        country (str): Country code to filter events by (e.g., 'AU', 'US', etc.).
        tz (ZoneInfo): Timezone to use for date calculations.
        default_vals (str, optional): internal use
        index (str, optional): internal use

    Returns:
        list[UpcomingEarningsEvent]: A list of upcoming earnings events
    """
    country = country.upper()
    end_date = calc_end_date_to_fetch_events(event_type="EARNINGS", tz=tz, index=index)
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


async def get_asx_upcoming_earnings_events(index: str = "") -> list[UpcomingEarningsEvent]:
    """
    Check for upcoming earnings events for ASX.

    Args:
        index (str, optional): ASX index to filter stocks (e.g. ASX20, ASX50, ASX100, ASX200 and ASX300)

    Returns:
        list[UpcomingEarningsEvent]: A list of upcoming earnings events
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
    events = await get_upcoming_earnings_events(country, tz, default_vals=default_vals, index=index)
    if index:
        events = [e for e in events if finhub_utils.is_in_index(e.symbol, index)]

    for event in events:
        event.link = f"https://www.tipranks.com/stocks/au:{event.symbol.lower().split(':')[-1]}/earnings"
    return events


async def get_us_upcoming_earnings_events(index: str = "") -> list[UpcomingEarningsEvent]:
    """
    Check for upcoming earnings events for US market.

    Args:
        index (str, optional): index to filter stocks (e.g. NASDAQ100, SP500, SP400 and SP600)

    Returns:
        list[UpcomingEarningsEvent]: A list of upcoming earnings events
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
    events = await get_upcoming_earnings_events(country, tz, default_vals=default_vals, index=index)
    if index:
        events = [e for e in events if finhub_utils.is_in_index(e.symbol, index)]

    for event in events:
        event.link = f"https://www.tipranks.com/stocks/{event.symbol.lower().split(':')[-1]}/earnings"
    return events


async def analyse_dividend_event(
    symbol: str, ex_div_date: str, div_amount: float, ticker: yf.Ticker = None
) -> models.DividendEventAnalysis | None:
    """
    Analyzes a dividend event to estimate price range and recovery probability.

    Args:
        symbol (str): Stock ticker symbol (e.g., 'AAPL', 'BHP.AX', 'HOSE:BID' etc.).
        ex_div_date (str): Ex-dividend date in ISO format (YYYY-MM-DD).
        div_amount (float): Dividend amount per share.
        ticker (yf.Ticker, optional): Pre-created yfinance Ticker object for the stock for reuse/caching purpose. If not provided, it will be created within the function.
    Returns:
        models.DividendEventAnalysis: An object containing the analysis of the dividend event
    """
    yf_ticker = finhub_utils.to_yf_ticker(symbol)
    country = finhub_utils.country_code_from_yf_ticker(yf_ticker)
    tz = finhub_utils.tz_from_yf_ticker(yf_ticker)

    ticker = yf.Ticker(yf_ticker) if ticker is None else ticker
    quote_type = ticker.info.get("quoteType")
    if quote_type == "NONE":
        return None  # no data available
    if quote_type not in allowed_quote_types:
        raise ValueError(f"Quote type '{quote_type}' for ticker '{ticker}' is not supported for dividend analysis.")

    current_price = ticker.info.get("regularMarketPrice")
    result = models.DividendEventAnalysis(
        overview=models.SymbolOverview(ticker),
        price=current_price,
        div_amount=div_amount,
        div_yield=div_amount / current_price,
        ex_div_date=finhub_utils.yyyy_mm_dd_to_iso(ex_div_date, tz=tz),
    )
    result.ex_div_date_timestamp = int(datetime.fromisoformat(result.ex_div_date).timestamp())

    history = ticker.history(period="5y", interval="1d", auto_adjust=False)
    history5y = history[:-1]
    if len(history5y) < 90:
        return None  # not enough data
    history5y = history5y.tz_convert(tz)

    past_dividends_analysis = finhub_utils.analyze_past_dividends(history5y, 28)
    if past_dividends_analysis.empty:
        return None  # not enough historical data
    result.num_samples = len(past_dividends_analysis)

    # estimate price drop
    avg_drop_ratio = past_dividends_analysis["DropRatio"].mean()
    std_drop_ratio = past_dividends_analysis["DropRatio"].std()
    min_drop = div_amount * (avg_drop_ratio - std_drop_ratio)
    max_drop = div_amount * (avg_drop_ratio + std_drop_ratio)
    result.drop_price_min = float(current_price - max_drop)
    result.drop_price_max = float(current_price - min_drop)

    # estimate recovery days
    median_recovery_days = past_dividends_analysis["RecoveryDays"].median()
    std_recovery_days = past_dividends_analysis["RecoveryDays"].std()
    result.recovery_days_min = int(median_recovery_days - std_recovery_days)
    result.recovery_days_max = int(median_recovery_days + std_recovery_days)

    # estimate recovery chance
    total_rows = len(past_dividends_analysis)
    num_recovery_max = (past_dividends_analysis["RecoveryDays"].notna()).sum()
    result.recovery_probability = float(num_recovery_max / total_rows)

    # estimate recovery price
    recovery_data = past_dividends_analysis[past_dividends_analysis["RecoveryDays"].notna()]
    if not recovery_data.empty:
        mean_overshoot = (recovery_data["PostExDivPeak"] - recovery_data["PreExDivPrice"]).mean()
        result.recovery_price_min = current_price
        result.recovery_price_max = float(current_price + mean_overshoot)

    # additional technical data
    result.beta = ticker.info.get("beta")
    history7d = history5y[-7:]
    history7d["DVT"] = (
        (history7d["Open"] + history7d["Close"] + history7d["High"] + history7d["Low"]) / 4 * history7d["Volume"]
    )
    result.avg_dvt_7d = int(history7d["DVT"].mean())
    result.std_dvt_7d = int(history7d["DVT"].std())
    history30d = history5y[-30:]
    result.rsi14 = int(finhub_utils.calc_rsi(history30d, 14).iloc[-1])
    result.avg_volume_30d = int(history30d["Volume"].mean())
    result.std_volume_30d = int(history30d["Volume"].std())
    result.bid_ask_spread = finhub_utils.calc_bid_ask_spread_roll(history[-30:])

    result.trend_60d = finhub_utils.calc_trend_ema(history5y[-60:])
    market_main_indices = finhub_utils.yf_tickers_for_market_indices(country)
    if market_main_indices and len(market_main_indices) > 0:
        market_ticker = yf.Ticker(market_main_indices[0])
        market_history60d = market_ticker.history(period="61d", interval="1d", auto_adjust=False)[:-1]
        market_history60d = market_history60d.tz_convert(tz)
        result.market_trend_60d = finhub_utils.calc_trend_ema(market_history60d)
    sector, industry = result.overview.sector, result.overview.industry
    market_industry_indices = finhub_utils.yf_tickers_for_market_indices(country, sector, industry)
    if market_industry_indices and len(market_industry_indices) > 0:
        industry_ticker = yf.Ticker(market_industry_indices[0])
        industry_history60d = industry_ticker.history(period="61d", interval="1d", auto_adjust=False)[:-1]
        industry_history60d = industry_history60d.tz_convert(tz)
        result.industry_trend_60d = finhub_utils.calc_trend_ema(industry_history60d)

    return result
