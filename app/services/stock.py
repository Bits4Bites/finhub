from datetime import datetime, timedelta
from typing import Any

import yfinance as yf

from .. import config
from ..models import market_data as models_market_data
from ..models import stocks as models_stocks
from ..utils import conv


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


def get_symbol_info(symbol: str) -> models_stocks.SymbolInfo | None:
    """
    Fetches detailed information about a ticker symbol.

    Args:
        symbol (str): The stock symbol to fetch information for, accepting YF format (e.g. ABC.AX) or EXCHANGE:CODE (e.g. NASDAQ:XYZ).

    Returns:
        models_stocks.SymbolInfo | None: Symbol information, or None.
    """
    yf_symbol = conv.to_yf_symbol_format(symbol)
    ticker = yf.Ticker(yf_symbol)
    quote_type = ticker.info.get("quoteType")
    if quote_type in config.ALLOWED_QUOTE_TYPES:
        return models_stocks.SymbolInfo(ticker)
    return None


def get_symbol_overview(symbol: str) -> models_stocks.SymbolOverview | None:
    """
    Fetches overview information about a ticker symbol.

    Args:
        symbol (str): The stock symbol to fetch information for, accepting YF format (e.g. ABC.AX) or EXCHANGE:CODE (e.g. NASDAQ:XYZ).

    Returns:
        models_stocks.SymbolOverview | None: Symbol overview information, or None.
    """
    yf_symbol = conv.to_yf_symbol_format(symbol)
    ticker = yf.Ticker(yf_symbol)
    quote_type = ticker.info.get("quoteType")
    if quote_type in config.ALLOWED_QUOTE_TYPES:
        return models_stocks.SymbolOverview(ticker)
    return None


def get_stock_quotes(symbols: list[str]) -> dict[str, models_market_data.StockQuote]:
    """
    Fetches stock quotes for a list of ticker symbols.

    Args:
        symbols (list[str]): A list of stock symbols to fetch quotes for, accepting YF format (e.g. ABC.AX) or EXCHANGE:CODE (e.g. NASDAQ:XYZ).

    Returns:
        dict[str, models_market_data.StockQuote]: Quotes keyed by requested symbol.
    """
    yf_symbols = [conv.to_yf_symbol_format(s) for s in symbols]
    tickers = yf.Tickers(" ".join(yf_symbols))
    quotes = {}
    for i in range(0, len(symbols)):
        yf_symbol = yf_symbols[i]
        if yf_symbol in tickers.tickers:
            ticker = tickers.tickers[yf_symbol]
            quote_type = ticker.info.get("quoteType") if ticker.info.get("quoteType") is not None else "NONE"
            if quote_type in config.ALLOWED_QUOTE_TYPES:
                symbol = symbols[i]
                quotes[symbol] = models_market_data.StockQuote(ticker)
    return quotes


def get_stock_quote_at_date(symbol: str, date_str: str) -> models_market_data.HistoryPoint | None:
    """
    Fetches stock quote information for a given ticker symbol at a specific date.

    Args:
        symbol (str): The stock symbol to fetch information for, accepting YF format (e.g. ABC.AX) or EXCHANGE:CODE (e.g. NASDAQ:XYZ).
        date_str (str): The date to fetch the quote for (format: YYYY-MM-DD).

    Returns:
        models_market_data.HistoryPoint | None: The quote for the requested date, or None.
    """
    yf_symbol = conv.to_yf_symbol_format(symbol)
    ticker = yf.Ticker(yf_symbol)
    quote_type = ticker.info.get("quoteType")
    if quote_type in config.ALLOWED_QUOTE_TYPES:
        try:
            start_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return None
        end_date = start_date + timedelta(days=1)
        start_date = start_date - timedelta(days=14)  # to account for weekends and holidays

        history = ticker.history(start=start_date, end=end_date, interval="1d", auto_adjust=False)
        if not history.empty:
            point = history.iloc[-1]
            return models_market_data.HistoryPoint(
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


def get_symbol_history(symbol: str, days: int = 100) -> list[models_market_data.HistoryPoint] | None:
    """
    Fetches historical stock price data for a given ticker symbol.

    Args:
        symbol (str): The stock symbol to fetch information for, accepting YF format (e.g. ABC.AX) or EXCHANGE:CODE (e.g. NASDAQ:XYZ).
        days (int): The number of days of historical data to retrieve (default is 100).

    Returns:
        list[models_market_data.HistoryPoint] | None: Historical prices, or None.
    """
    yf_symbol = conv.to_yf_symbol_format(symbol)
    ticker = yf.Ticker(yf_symbol)
    quote_type = ticker.info.get("quoteType")
    if quote_type in config.ALLOWED_QUOTE_TYPES:
        num_days = 100 if days <= 0 else days
        hist = ticker.history(period=f"{num_days}d", interval="1d", auto_adjust=False)
        points = [
            models_market_data.HistoryPoint(
                timestamp=int(hist.index[i].timestamp()),
                timestamp_str=hist.index[i].isoformat(sep=" ", timespec="seconds"),
                open=hist.iloc[i]["Open"],
                high=hist.iloc[i]["High"],
                low=hist.iloc[i]["Low"],
                close=hist.iloc[i]["Close"],
                volume=int(hist.iloc[i]["Volume"]),
            )
            for i in range(0, len(hist))
        ]
        return points

    return None
