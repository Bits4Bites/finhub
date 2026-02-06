from typing import Any

import yfinance as yf
from ..models.finhub import SymbolInfo, StockQuote


async def get_symbol_info(symbol: str) -> SymbolInfo:
    """
    Fetches detailed information about a ticker symbol.

    :param symbol: The ticker symbol to fetch information for.
    :type symbol: str
    :return: A SymbolInfo object containing detailed information about the ticker symbol.
    :rtype: SymbolInfo
    """
    ticker = yf.Ticker(symbol)
    return SymbolInfo(symbol=symbol, ticker=ticker)


def get_symbol_info_raw(symbol: str) -> dict[str, Any]:
    """
    Fetches detailed information about a ticker symbol.

    :param symbol: The ticker symbol to fetch information for.
    :type symbol: str
    :return: A dictionary containing the raw ticker information.
    :rtype: dict[str, Any]
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


def get_stock_quotes(symbols: list[str]) -> dict[str, StockQuote]:
    """
    Fetches stock quotes for a list of ticker symbols.

    :param symbols: A list of ticker symbols to fetch quotes for.
    :type symbols: list[str]
    :return: A list of SymbolInfo objects containing stock quotes for the requested symbols.
    :rtype: list[SymbolInfo]
    """
    tickers = yf.Tickers(" ".join(symbols))
    quotes = {}
    for symbol in symbols:
        ticker = tickers.tickers[symbol]
        quotes[symbol] = StockQuote(ticker)

    return quotes
