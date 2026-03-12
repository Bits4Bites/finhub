from datetime import datetime, timedelta
from typing import Any

import yfinance as yf
from ..models.finhub import SymbolInfo, StockQuote, SymbolOverview, HistoryPoint

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
                open=point["Open"],
                high=point["High"],
                low=point["Low"],
                close=point["Close"],
                volume=point["Volume"],
                dividends=point["Dividends"],
            )
    return None
