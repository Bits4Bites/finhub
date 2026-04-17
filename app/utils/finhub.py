from datetime import datetime
from zoneinfo import ZoneInfo

import country_converter as coco
import numpy as np
import pandas as pd
import yfinance as yf

from .data import (
    asx_index_yf_static_tickers,
    asx_sector_yf_static_tickers,
    us_index_yf_static_tickers,
    us_sector_yf_static_tickers,
    us_industry_yf_static_tickers,
)
from .. import config
from ..models import types


def country_to_iso2(country: str) -> str:
    """
    Converts a country (name/code) to an ISO 3166-1 alpha-2 country code.

    Args:
        country (str): The country (name, code) to convert.

    Returns:
        str: The ISO 3166-1 alpha-2 country code.
    """
    return coco.convert(names=country, to="ISO2")


def normalize_exchange_code(exchange: str) -> str:
    """
    Normalize an exchange name to unified code (e.g. NYSE, NASDAQ...)
    """
    e = exchange.upper()
    return "NASDAQ" if "NASDAQ" in e else "NYSE" if "NY" in e else e


def lookup_market_yf_static_ticker(
    *,
    ticker: yf.Ticker = None,
    symbol: str = None,
) -> str | None:
    """
    Lookup a "market static ticker" (YF format) for a given stock.
    For example "market static ticker" for CBA.AX should be ASX20/ASX50, "market static ticker" for AAPL should be NASDAQ100.

    Args:
        ticker (yf.Ticker): The stock to look up market ticker for.
        symbol (str): The stock symbol to look up market ticker for.

    Returns:
        str: The market static ticker as a Yahoo Finance ticker.

    Remarks:
        Only supply either ticker or symbol. If both are supplied, tickr takes precedence.
    """
    if ticker is not None:
        symbol = to_exchange_ticker(ticker=ticker) or ""
    else:
        symbol = to_exchange_ticker(symbol=symbol) or ""
    exchange = symbol.split(":")[0]
    if exchange == "ASX":
        for index in asx_index_yf_static_tickers.keys():
            if is_in_index(index=index, symbol=symbol):
                return asx_index_yf_static_tickers[index]
        return asx_index_yf_static_tickers["ASX"]
    if exchange == "NASDAQ":
        return (
            us_index_yf_static_tickers["NASDAQ100"]
            if is_in_index(index="NASDAQ100", symbol=symbol)
            else us_index_yf_static_tickers["NASDAQ"]
        )
    if exchange == "NYSE":
        for index in ["SP500", "SP400", "SP600"]:
            if is_in_index(index=index, symbol=symbol):
                return us_index_yf_static_tickers[index]
        return us_index_yf_static_tickers["DOWJONES"]

    return None


def lookup_peer_yf_static_ticker(
    *,
    ticker: yf.Ticker = None,
    symbol: str = None,
    sector: str = None,
    industry: str = None,
) -> str | None:
    """
    Lookup a "market static ticker" (YF format) for a given stock.
    For example "market static ticker" for CBA.AX should be ASX20/ASX50, "market static ticker" for AAPL should be NASDAQ100.

    Args:
        ticker (yf.Ticker): The stock to look up market ticker for.
        symbol (str): The stock symbol to look up market ticker for.
        sector (str): The sector to look up market ticker for.
        industry (str, optional): The industry to filter for.

    Returns:
        str: The market static ticker as a Yahoo Finance ticker.

    Remarks:
        Only supply either ticker or symbol/sector/industry. If both are supplied, tickr takes precedence.
    """
    if ticker is not None:
        symbol = to_exchange_ticker(ticker=ticker) or ""
        sector = ticker.info.get("sector", "")
        industry = ticker.info.get("industry", "")
    else:
        symbol = to_exchange_ticker(symbol=symbol) or ""
    exchange = symbol.split(":")[0]
    sector = sector.upper() if sector else ""
    industry = industry.upper() if industry else ""
    if exchange == "ASX":
        if sector in asx_sector_yf_static_tickers:
            return asx_sector_yf_static_tickers[sector]
    if exchange == "NASDAQ" or exchange == "NYSE":
        if sector in us_industry_yf_static_tickers and industry in us_industry_yf_static_tickers[sector]:
            return us_industry_yf_static_tickers[sector][industry]
        if sector in us_sector_yf_static_tickers:
            return us_sector_yf_static_tickers[sector]

    return None


def number_to_human_format(num: int | float, precision: int = 2):
    """
    Convert a number into a human-readable format with K, M, B, T suffixes.

    Args:
        num (int|float): The number to format.
        precision (int): Decimal places to keep.

    Returns:
        str: Formatted string.
    """
    # Handle negative numbers
    sign = "-" if num < 0 else ""
    num = abs(num)

    # Define suffixes
    suffixes = ["", "K", "M", "B", "T"]
    idx = 0

    # Scale down the number
    while num >= 1000 and idx < len(suffixes) - 1:
        num /= 1000.0
        idx += 1

    # Format with given precision
    formatted = f"{num:.{precision}f}".rstrip("0").rstrip(".")
    return f"{sign}{formatted}{suffixes[idx]}"


def tz_from_yf_ticker(yf_ticker: str) -> ZoneInfo:
    """
    Gets the timezone for a Yahoo Finance ticker.

    Args:
        yf_ticker (str): The ticker for the Yahoo Finance ticker (e.g. CBA.AX or APPL).

    Returns:
        ZoneInfo: The timezone for the Yahoo Finance ticker, default is America/New_York
    """
    yf_ticker = yf_ticker.upper()
    if yf_ticker.endswith(".AX"):
        return ZoneInfo("Australia/Sydney")
    elif yf_ticker.endswith(".VN"):
        return ZoneInfo("Asia/Ho_Chi_Minh")
    else:
        return ZoneInfo("America/New_York")


def country_code_from_yf_ticker(yf_ticker: str) -> str:
    """
    Gets the country code for a Yahoo Finance ticker.

    Args:
        yf_ticker (str): The ticker for the Yahoo Finance ticker (e.g. CBA.AX or APPL).

    Returns:
        str: The country code for the Yahoo Finance ticker, default is US
    """
    yf_ticker = yf_ticker.upper()
    if yf_ticker.endswith(".AX"):
        return "AU"
    elif yf_ticker.endswith(".VN"):
        return "VN"
    else:
        return "US"


def yyyy_mm_dd_to_iso(yyyy_mm_dd: str, tz: ZoneInfo = None, tz_name: str = None) -> str | None:
    """
    Converts a date string in the format 'YYYY-MM-DD' to ISO format 'YYYY-MM-DD 00:00:00+hh:mm'.

    Args:
        yyyy_mm_dd (str): The date in the format YYYY-MM-DD
        tz (ZoneInfo, optional): The timezone to use. Defaults to None.
        tz_name (str, optional): The timezone to use. Defaults to None.

    Returns:
        str: The date in ISO format, or None if the input date string is invalid.

    Remarks:
        If both tz and tz_name are provided, tz will be used.
    """
    tz = tz or (ZoneInfo(tz_name) if tz_name else ZoneInfo("UTC"))
    try:
        return datetime.strptime(yyyy_mm_dd, "%Y-%m-%d").replace(tzinfo=tz).isoformat(sep=" ", timespec="seconds")
    except ValueError:
        return None


def to_exchange_ticker(*, ticker: yf.Ticker = None, symbol: str = None) -> str | None:
    """
    Converts a stock symbol to EXCHANGE:CODE format
    - If symbol is already in format EXCHANGE:CODE, it is returned as is.
    - If symbol is in YF format (e.g., "AAPL", "CBA.AX" or "BID.VN"), try best to convert to EXCHANGE:CODE.
    - Otherwise, return symbol as is.

    Args:
        ticker (yf.Ticker, optional): The ticker to convert to EXCHANGE:CODE.
        symbol (str): The stock symbol to convert to EXCHANGE:CODE format.

    Returns:
        str: The stock symbol as EXCHANGE:CODE.

    Remarks:
        Supply either ticker or symbol. If both are supplied, ticker takes precedence.
    """
    if ticker is None and symbol is None:
        return None

    symbol = symbol or ""
    if ticker is None and ":" in symbol:
        return symbol.upper()

    ticker = yf.Ticker(symbol) if ticker is None else ticker
    exchange = normalize_exchange_code(ticker.info.get("fullExchangeName", ticker.info.get("exchange", "")))
    symbol = ticker.info.get("symbol", "")
    if symbol.endswith(".VN") or symbol.endswith(".AX"):
        return f"{exchange}:{symbol[:-3]}"
    else:
        return f"{exchange}:{symbol}"


def to_yf_ticker(symbol: str) -> str:
    """
    Converts a stock symbol to a Yahoo Finance ticker format.
    - If symbol is already in YF format (e.g., "AAPL", "CBA.AX" or "BID.VN"), return as is.
    - If symbol is in format EXCHANGE:CODE (e.g., "ASX:CBA", "HOSE:BID"), convert to YF format (e.g., "CBA.AX", "BID.VN").
    - Otherwise, return symbol as is.

    Args:
        symbol (str): The stock symbol to convert to YF ticker format.

    Returns:
        str: The stock symbol as a Yahoo Finance ticker.
    """
    symbol = symbol.upper()
    if ":" in symbol:
        exchange, ticker = symbol.split(":", 1)
        if exchange == "ASX":
            return f"{ticker}.AX"
        elif exchange == "HOSE" or exchange == "HNX" or exchange == "UPCOM":
            return f"{ticker}.VN"
        elif exchange == "NYSE" or exchange == "NASDAQ":
            return ticker
    return symbol


def is_in_index(*, index: str, ticker: yf.Ticker = None, symbol: str = None) -> bool:
    """
    Checks if a stock symbol in a market index.

    Args:
        index (str): The market index.
        ticker (yf.Ticker): The stock ticker to check
        symbol (str): The stock symbol to check, should be in format EXCHANGE:CODE.

    Returns:
        bool: True if the stock symbol in a market index, False otherwise.

    Remarks:
        Supply either ticker or symbol. If both are supplied, ticker takes precedence.
    """
    index = index.upper()
    if index in config.market_indices.indices:
        if ticker is not None:
            symbol = to_exchange_ticker(ticker=ticker) or ""
        else:
            symbol = to_exchange_ticker(symbol=symbol) or ""
        return symbol in config.market_indices.indices[index]
    return False


def classify_market_cap(
    ticker: yf.Ticker = None, /, country: str = None, exchange_symbol: str = None, market_cap: int = None
) -> tuple[types.MarketCapType | None, str | None]:
    """
    Classifies a stock market cap.

    Args:
        ticker (yf.Ticker): The stock ticker to classify.
        country (str): The country to classify (ISO2 country code).
        exchange_symbol (str): The exchange ticker to classify (format EXCHANGE:CODE).
        market_cap (int): The market cap to classify.

    Returns:
        tuple[models.MarketCapType|None, str|None]: classified market cap and optional index

    Remarks:
        Supply either ticker or tuple[country, exchange_ticker, market_cap]. If both are supplied, ticker will be used.
    """
    cap_size: types.MarketCapType = None
    market_index = None
    if ticker is not None:
        country = country_to_iso2(ticker.info.get("country", ticker.info.get("region", "US")))
        exchange = normalize_exchange_code(ticker.info.get("fullExchangeName", ticker.info.get("exchange", "")))
        symbol = ticker.info.get("symbol", "").upper()
        if country != "US":
            # e.g. AU or VN
            symbol = symbol.split(".")[0]
        exchange_symbol = f"{exchange}:{symbol}"
        market_cap = int(ticker.info.get("marketCap", 0))

    exchange_symbol = exchange_symbol or ""
    market_cap = market_cap or 0
    if country == "AU" or country == "US":
        if market_cap >= 10_000_000_000:
            cap_size = types.LARGE_CAP
        elif market_cap >= 2_000_000_000:
            cap_size = types.MID_CAP
        elif market_cap >= 300_000_000:
            cap_size = types.SMALL_CAP
        elif market_cap >= 50_000_000:
            cap_size = types.MICRO_CAP
        else:
            cap_size = types.NANO_CAP

        for index in ["ASX50", "NASDAQ100", "SP500"]:
            # if listed in any of these indexes, definitely Large
            if is_in_index(index=index, symbol=exchange_symbol):
                market_index = index
                cap_size = types.LARGE_CAP
                break
        if is_in_index(index="SP400", symbol=exchange_symbol):
            market_index = "SP400"
            cap_size = types.MID_CAP
        if is_in_index(index="SP600", symbol=exchange_symbol):
            market_index = "SP600"
            cap_size = types.SMALL_CAP

        if market_index is None:
            if is_in_index(index="ASX100", symbol=exchange_symbol):
                # if in ASX100, move up 1 tier (mid -> large, small -> mid)
                market_index = "ASX100"
                if cap_size == types.MID_CAP:
                    cap_size = types.LARGE_CAP
                elif cap_size == types.SMALL_CAP:
                    cap_size = types.MID_CAP
            elif not is_in_index(index="ASX300", symbol=exchange_symbol):
                # if outside ASX300, move down 1 tier (mid -> small, small -> micro)
                if cap_size == types.SMALL_CAP:
                    cap_size = types.MICRO_CAP
                elif cap_size == types.MID_CAP:
                    cap_size = types.SMALL_CAP

        if market_index is None:
            for index in ["ASX50", "ASX100", "ASX200", "ASX300"]:
                if is_in_index(index=index, symbol=exchange_symbol):
                    market_index = index
                    break

    if country == "VN":
        if market_cap >= 10_000_000_000_000:
            cap_size = types.LARGE_CAP
        elif market_cap >= 1_000_000_000_000:
            cap_size = types.MID_CAP
        elif market_cap >= 100_000_000_000:
            cap_size = types.SMALL_CAP
        elif market_cap >= 10_000_000_000:
            cap_size = types.MICRO_CAP
        else:
            cap_size = types.NANO_CAP

        if exchange_symbol.startswith("HOSE:"):
            if is_in_index(index="VN30", symbol=exchange_symbol):
                # in VN30 --> Large
                market_index = "VN30"
                cap_size = types.LARGE_CAP
            elif is_in_index(index="VN100", symbol=exchange_symbol):
                # in VN100 --> Mid
                market_index = "VN100"
                cap_size = types.MID_CAP
            else:
                # down 1 level
                if cap_size == types.MID_CAP:
                    cap_size = types.SMALL_CAP
                elif cap_size == types.LARGE_CAP:
                    cap_size = types.MID_CAP

        if exchange_symbol.startswith("HNX:"):
            if is_in_index(index="HNX30", symbol=exchange_symbol):
                market_index = "HN30"
                if cap_size == types.SMALL_CAP:
                    cap_size = types.MID_CAP
            else:
                # down 1 level
                if cap_size == types.MID_CAP:
                    cap_size = types.SMALL_CAP
                elif cap_size == types.LARGE_CAP:
                    cap_size = types.MID_CAP

    return cap_size, market_index


def calc_rsi(data: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """
    Calculates the Relative Strength Index (RSI) for a given DataFrame of stock prices.

    Args:
        data (DataFrame): The DataFrame of stock prices (obtained from yfinance) with a 'Close' column.
        period (int, optional): The number of periods to use for the RSI calculation. Defaults to 14.

    Returns:
        DataFrame: A DataFrame containing the RSI values, with the same index as the input data.
    """
    delta = data["Close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calc_trend_sma(data: pd.DataFrame, short: int = 50, long: int = 100) -> float:
    """
    Calculates the trend over the period of the data using SMA comparison method.

    Args:
        data (DataFrame): The DataFrame of stock prices (obtained from yfinance) with a 'Close' column.
        short (int, optional): The number of periods to use for the SMA calculation. Defaults to 50.
        long (int, optional): The number of periods to use for the SMA calculation. Defaults to 100.

    Returns:
        float: The trend over the period of the stock prices (MA-short - MA-long) / MA-long
    """
    if len(data) < long or len(data) < short:
        return 0
    sma_short = data["Close"].rolling(window=short).mean()
    sma_long = data["Close"].rolling(window=long).mean()
    result = float((sma_short.iloc[-1] - sma_long.iloc[-1]) / sma_long.iloc[-1])
    return result


def calc_trend_ema(data: pd.DataFrame, short: int = 21, long: int = 55) -> float:
    """
    Calculates the trend over the period of the data using EMA comparison method.

    Args:
        data (DataFrame): The DataFrame of stock prices (obtained from yfinance) with a 'Close' column.
        short (int, optional): The number of periods to use for the SMA calculation. Defaults to 21.
        long (int, optional): The number of periods to use for the SMA calculation. Defaults to 55.

    Returns:
        float: The trend over the period of the stock prices (MA-short - MA-long) / MA-long
    """
    if len(data) < long or len(data) < short:
        return 0
    ema_short = data["Close"].ewm(span=short).mean()
    ema_long = data["Close"].ewm(span=long).mean()
    result = float((ema_short.iloc[-1] - ema_long.iloc[-1]) / ema_long.iloc[-1])
    return result


def find_volume_spikes(data: pd.DataFrame, threshold_multiplier: float = 2.5) -> pd.DataFrame:
    """
    Identifies volume spikes in the stock data.
    A volume spike is defined as a day when the trading volume is greater than the average volume over the period multiplied by the threshold_multiplier.
    """
    avg_volume = data["Volume"].mean()
    threshold = avg_volume * threshold_multiplier
    spikes = data[data["Volume"] >= threshold]
    return spikes


def analyze_past_dividends(data: pd.DataFrame, recovery_days_threshold: int = 28) -> pd.DataFrame:
    """
    Analyzes the past dividends over the period of the stock data.

    Args:
        data (DataFrame): The DataFrame of stock prices (obtained from yfinance) with 'Close' and 'Dividends' column.
        recovery_days_threshold (int, optional): The number of days to look for price recovery after the ex-dividend date. Defaults to 28.

    Returns:
        DataFrame: A DataFrame containing the dividend analysis, with the same index as the input data, containing columns for dividend analysis
    """
    # Algorithm:
    # - Ex-Div date is the date where fields Dividends > 0
    # - For each Ex-Div date:
    #   - Get value of Close field of the previous date (PreExDivPrice)
    #   - For the next recovery_days_threshold days, check for the first date where Close price >= PreExDivPrice, or None if not found
    dividend_data = data[data["Dividends"] > 0].copy()
    if dividend_data.empty:
        return dividend_data
    if recovery_days_threshold < 1:
        recovery_days_threshold = 10

    dividend_data["DVT"] = (
        (dividend_data["Open"] + dividend_data["Close"] + dividend_data["High"] + dividend_data["Low"])
        / 4
        * dividend_data["Volume"]
    )
    dividend_data = dividend_data[["Dividends", "Open", "Close", "Volume", "DVT"]]
    dividend_data["PreExDivPrice"] = data["Close"].shift(1)
    # for t in [1,3,5,10,20,30]:
    #     dividend_data[f"DRE{t}"] = (data["Close"].shift(-t)-dividend_data["PreExDivPrice"]) / (dividend_data["Dividends"]*sqrt(t))

    # dividend_data["Drop"] = dividend_data["PreExDivPrice"] - dividend_data["Open"]  # drop amount
    # # set to 0 if Drop < 0
    # # dividend_data["Drop"] = dividend_data["Drop"].apply(lambda x: x if x > 0 else 0)
    # dividend_data["DropRatio"] = dividend_data["Drop"] / dividend_data["Dividends"]

    dividend_data["RecoveryDays"] = None
    dividend_data["PostExDivPeak"] = None
    dividend_data["PostExDivFloor"] = None
    for idx in dividend_data.index:
        pre_ex_div_price = dividend_data.at[idx, "PreExDivPrice"]
        for i in range(1, recovery_days_threshold + 1):
            if idx + pd.Timedelta(days=i) in data.index:
                close_price = data.at[idx + pd.Timedelta(days=i), "Close"]
                if (
                    dividend_data.at[idx, "PostExDivPeak"] is None
                    or close_price > dividend_data.at[idx, "PostExDivPeak"]
                ):
                    # peak price can continue after recovery
                    dividend_data.at[idx, "PostExDivPeak"] = close_price
                if dividend_data.at[idx, "PostExDivFloor"] is None or (
                    close_price < dividend_data.at[idx, "PostExDivFloor"]
                    and dividend_data.at[idx, "RecoveryDays"] is None
                ):
                    # only set floor price if not recovered yet
                    dividend_data.at[idx, "PostExDivFloor"] = close_price
                if (
                    close_price >= pre_ex_div_price
                    and dividend_data.at[idx, "Volume"] > 0
                    and dividend_data.at[idx, "RecoveryDays"] is None
                ):
                    # recovery day is the first day close_price >= pre_ex_div_price and has transacted volume
                    dividend_data.at[idx, "RecoveryDays"] = i

    # price might drop a few days later, not exactly on the ex-div day
    dividend_data["Drop"] = dividend_data["PreExDivPrice"] - dividend_data["PostExDivFloor"]
    dividend_data["DropRatio"] = dividend_data["Drop"] / dividend_data["Dividends"]

    return dividend_data


def calc_bid_ask_spread_roll(data: pd.DataFrame) -> float | None:
    """
    Calculates the bid/ask spread over the period of the stock data, using Roll’s Estimator

    Args:
        data (DataFrame): The DataFrame of stock prices (obtained from yfinance) with 'Close' column.

    Returns:
        float: The bid/ask spread over the period of the stock data, calculated using Roll’s Estimator
    """
    if len(data) < 2:
        return None
    data = data.copy()
    data["Price_Change"] = data["Close"].diff()
    data["Prev_Price_Change"] = data["Price_Change"].shift(1)

    # Calculate covariance between today's change and yesterday's change
    cov = data["Price_Change"].cov(data["Prev_Price_Change"])

    if cov < 0:
        # Roll's formula
        estimated_spread_dollar = 2 * np.sqrt(-cov)
        latest_close = data["Close"].iloc[-1]
        estimated_spread = estimated_spread_dollar / latest_close
        return float(estimated_spread)

    # Roll's Estimator failed (Covariance is positive). Stock is trending too hard.
    return None
