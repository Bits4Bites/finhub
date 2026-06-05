from datetime import datetime, timedelta
from typing import Any

import yfinance as yf

from .. import config
from ..models import finhub as models
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


def get_symbol_info(symbol: str) -> models.SymbolInfo | None:
    """
    Fetches detailed information about a ticker symbol.

    Args:
        symbol (str): The stock symbol to fetch information for, accepting YF format (e.g. ABC.AX) or EXCHANGE:CODE (e.g. NASDAQ:XYZ).

    Returns:
        models.SymbolInfo | None: A models.SymbolInfo object containing the information about the symbol, or None.
    """
    yf_symbol = conv.to_yf_symbol_format(symbol)
    ticker = yf.Ticker(yf_symbol)
    quote_type = ticker.info.get("quoteType")
    if quote_type in config.ALLOWED_QUOTE_TYPES:
        return models.SymbolInfo(ticker)
    return None


def get_symbol_overview(symbol: str) -> models.SymbolOverview | None:
    """
    Fetches overview information about a ticker symbol.

    Args:
        symbol (str): The stock symbol to fetch information for, accepting YF format (e.g. ABC.AX) or EXCHANGE:CODE (e.g. NASDAQ:XYZ).

    Returns:
        models.SymbolOverview | None: A models.SymbolOverview object containing the overview information about the symbol, or None.
    """
    yf_symbol = conv.to_yf_symbol_format(symbol)
    ticker = yf.Ticker(yf_symbol)
    quote_type = ticker.info.get("quoteType")
    if quote_type in config.ALLOWED_QUOTE_TYPES:
        return models.SymbolOverview(ticker)
    return None


def get_stock_quotes(symbols: list[str]) -> dict[str, models.StockQuote]:
    """
    Fetches stock quotes for a list of ticker symbols.

    Args:
        symbols (list[str]): A list of stock symbols to fetch quotes for, accepting YF format (e.g. ABC.AX) or EXCHANGE:CODE (e.g. NASDAQ:XYZ).

    Returns:
        dict[str, models.StockQuote]: A dictionary mapping each symbol to its corresponding models.StockQuote object.
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
                quotes[symbol] = models.StockQuote(ticker)
    return quotes


def get_stock_quote_at_date(symbol: str, date_str: str) -> models.HistoryPoint | None:
    """
    Fetches stock quote information for a given ticker symbol at a specific date.

    Args:
        symbol (str): The stock symbol to fetch information for, accepting YF format (e.g. ABC.AX) or EXCHANGE:CODE (e.g. NASDAQ:XYZ).
        date_str (str): The date to fetch the quote for (format: YYYY-MM-DD).

    Returns:
        models.HistoryPoint | None: A models.HistoryPoint object containing the quote information for the symbol at the specified date, or None.
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
            return models.HistoryPoint(
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
