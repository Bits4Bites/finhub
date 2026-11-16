import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import yfinance as yf

from .. import config
from ..models import market_data as models_market_data
from ..models import stocks as models_stocks
from ..utils import conv


@dataclass(frozen=True)
class ResolvedSymbol:
    symbol: str
    normalized_symbol: str
    exchange: str
    country: str
    currency: str
    quote_type: str
    company_name: str | None
    market_price: float | None


def resolve_symbol(symbol: str) -> ResolvedSymbol:
    """Resolve a stock identifier into its Yahoo and canonical market identity.

    Args:
        symbol: A Yahoo symbol or an ``EXCHANGE:CODE`` identifier.

    Returns:
        The provider symbol, exchange-qualified symbol, market metadata, and a
        positive current price when one is available.

    Notes:
        ``regularMarketPrice`` is preferred over ``currentPrice``. Missing or
        non-positive prices produce ``None``. Missing country metadata defaults
        to the United States. Provider and symbol-conversion errors propagate.
    """
    yf_symbol = conv.to_yf_symbol_format(symbol)
    ticker = yf.Ticker(yf_symbol)
    info = dict(ticker.info or {})
    market_price = _positive_finite_number(info.get("regularMarketPrice"))
    if market_price is None:
        market_price = _positive_finite_number(info.get("currentPrice"))
    return ResolvedSymbol(
        symbol=str(info.get("symbol") or yf_symbol).strip().upper(),
        normalized_symbol=conv.to_exch_symb_format(ticker=ticker).strip().upper(),
        exchange=conv.normalize_exchange_code(str(info.get("fullExchangeName") or info.get("exchange") or "")),
        country=conv.country_to_iso2(str(info.get("country") or info.get("region") or "US")),
        currency=str(info.get("currency") or "").strip().upper(),
        quote_type=str(info.get("quoteType") or "").strip().upper(),
        company_name=str(info.get("longName") or info.get("shortName") or "").strip() or None,
        market_price=market_price,
    )


def _positive_finite_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    number = float(value)
    return number if math.isfinite(number) and number > 0 else None


def get_symbol_info_raw(symbol: str) -> dict[str, Any]:
    """Fetch provider metadata using Python-friendly field names.

    Args:
        symbol: The Yahoo Finance symbol to query.

    Returns:
        The provider metadata with camelCase keys converted to snake_case.

    Notes:
        Metadata values are preserved unchanged. Provider failures propagate.
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
    """Build detailed information for a supported financial security.

    Args:
        symbol: A Yahoo symbol or an ``EXCHANGE:CODE`` identifier.

    Returns:
        Detailed symbol information when Yahoo reports an equity
        (``EQUITY``), ETF (``ETF``), or mutual fund (``MUTUALFUND``);
        otherwise ``None``.

    Notes:
        Provider, conversion, and model-validation failures propagate.
    """
    yf_symbol = conv.to_yf_symbol_format(symbol)
    ticker = yf.Ticker(yf_symbol)
    quote_type = ticker.info.get("quoteType")
    if quote_type in config.ALLOWED_QUOTE_TYPES:
        return models_stocks.SymbolInfo(ticker)
    return None


def get_symbol_overview(symbol: str) -> models_stocks.SymbolOverview | None:
    """Build a market overview for a supported financial security.

    Args:
        symbol: A Yahoo symbol or an ``EXCHANGE:CODE`` identifier.

    Returns:
        Overview information when Yahoo reports an equity (``EQUITY``), ETF
        (``ETF``), or mutual fund (``MUTUALFUND``); otherwise ``None``.

    Notes:
        Provider, conversion, and model-validation failures propagate.
    """
    yf_symbol = conv.to_yf_symbol_format(symbol)
    ticker = yf.Ticker(yf_symbol)
    quote_type = ticker.info.get("quoteType")
    if quote_type in config.ALLOWED_QUOTE_TYPES:
        return models_stocks.SymbolOverview(ticker)
    return None


def get_stock_quotes(symbols: list[str]) -> dict[str, models_market_data.StockQuote]:
    """Fetch current quotes for supported financial securities.

    Args:
        symbols: Yahoo symbols or ``EXCHANGE:CODE`` identifiers.

    Returns:
        Quotes for equities (``EQUITY``), ETFs (``ETF``), and mutual funds
        (``MUTUALFUND``), keyed by the original requested symbols. Missing
        symbols and other or missing quote types are omitted. An empty input
        returns an empty dictionary. Included entries retain request order.

    Notes:
        Provider, conversion, and model-validation failures propagate.
    """
    if not symbols:
        return {}

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
    """Fetch the latest available daily quote on or before a requested date.

    Args:
        symbol: A Yahoo symbol or an ``EXCHANGE:CODE`` identifier.
        date_str: Requested date in strict, zero-padded ``YYYY-MM-DD`` format.

    Returns:
        The most recent daily quote on or before the requested date within the
        preceding 14 calendar days for an equity (``EQUITY``), ETF (``ETF``),
        or mutual fund (``MUTUALFUND``). Returns ``None`` for an invalid or
        non-zero-padded date, another or missing quote type, or unavailable
        history.

    Notes:
        Provider, conversion, and model-validation failures propagate.
    """
    yf_symbol = conv.to_yf_symbol_format(symbol)
    ticker = yf.Ticker(yf_symbol)
    quote_type = ticker.info.get("quoteType")
    if quote_type in config.ALLOWED_QUOTE_TYPES:
        try:
            requested_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return None
        if requested_date.strftime("%Y-%m-%d") != date_str:
            return None
        end_date = requested_date + timedelta(days=1)
        start_date = requested_date - timedelta(days=14)

        history = ticker.history(start=start_date, end=end_date, interval="1d", auto_adjust=False)
        if not history.empty:
            eligible_history = history[
                (history.index.date >= start_date) & (history.index.date <= requested_date)
            ].sort_index()
            if eligible_history.empty:
                return None
            point = eligible_history.iloc[-1]
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
    """Fetch ordered daily price history for a supported financial security.

    Args:
        symbol: A Yahoo symbol or an ``EXCHANGE:CODE`` identifier.
        days: Requested history length. Non-positive values use 100 days.

    Returns:
        History points in provider order for equities (``EQUITY``), ETFs
        (``ETF``), and mutual funds (``MUTUALFUND``), or an empty list when no
        observations are available. Returns ``None`` for another or missing
        quote type.

    Notes:
        Provider, conversion, and model-validation failures propagate.
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
