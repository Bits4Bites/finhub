from datetime import datetime
from zoneinfo import ZoneInfo

import country_converter as coco
import yfinance as yf

# Singleton converter instance (avoids repeated init overhead)
_COUNTRY_CONVERTER = coco.CountryConverter()


def country_to_iso2(country: str | None) -> str:
    """
    Converts a country (name/code) to an ISO 3166-1 alpha-2 country code.

    Args:
        country (str): The country (name, code) to convert.

    Returns:
        str: The ISO 3166-1 alpha-2 country code.
    """
    if not country:
        return ""
    code = _COUNTRY_CONVERTER.convert(country, to="ISO2")
    return code if code != "not found" else ""


# Mapping of known exchange name variants to canonical codes
_EXCHANGE_ALIASES: dict[str, str] = {
    "NMS": "NASDAQ",
    "NGM": "NASDAQ",
    "NCM": "NASDAQ",
    "NASDAQ": "NASDAQ",
    "NYQ": "NYSE",
    "NYSE": "NYSE",
    "NYS": "NYSE",
}


def normalize_exchange_code(exchange: str) -> str:
    """
    Normalize an exchange name to a unified code (e.g. NYSE, NASDAQ, ASX...).
    Uses a lookup table for known aliases, falls back to uppercase input.
    """
    e = exchange.strip().upper()
    if e in _EXCHANGE_ALIASES:
        return _EXCHANGE_ALIASES[e]
    if "NASDAQ" in e:
        return "NASDAQ"
    if "NY" in e:
        return "NYSE"
    return e


def to_exch_symb_format(*, ticker: yf.Ticker = None, symbol: str = None) -> str:
    """
    Converts a stock symbol to EXCHANGE:CODE format.
    - If symbol is already in format EXCHANGE:CODE, it is returned as is.
    - If symbol is in YF format (e.g., "AAPL", "CBA.AX" or "BID.VN"), try best to convert to EXCHANGE:CODE.
    - Otherwise, return symbol as is.

    Args:
        ticker (yf.Ticker): The ticker to convert to EXCHANGE:CODE format.
        symbol (str): The stock symbol to convert to EXCHANGE:CODE format.

    Returns:
        str: The stock symbol as EXCHANGE:CODE.

    Remarks:
        Supply either ticker or symbol. If both are supplied, ticker takes precedence.
    """
    if not ticker and not symbol:
        return ""

    symbol = symbol or ""
    if not ticker and ":" in symbol:
        return symbol.upper()

    ticker = yf.Ticker(symbol) if not ticker else ticker
    exchange = normalize_exchange_code(ticker.info.get("fullExchangeName", ticker.info.get("exchange", "")))
    symbol = ticker.info.get("symbol", "")
    # Strip YF exchange suffix if it's a 2-char country code (e.g. .AX, .VN, .TO)
    # Preserves dots in ticker names like BRK.B
    if "." in symbol:
        base, suffix = symbol.rsplit(".", 1)
        if len(suffix) == 2:
            symbol = base
    return f"{exchange}:{symbol}"


def to_yf_symbol_format(symbol: str) -> str:
    """
    Converts a stock symbol to a Yahoo Finance ticker format.
    - If symbol is already in YF format (e.g., "AAPL", "CBA.AX" or "BID.VN"), return as is.
    - If symbol is in format EXCHANGE:CODE (e.g., "ASX:CBA", "HOSE:BID"), convert to YF format (e.g., "CBA.AX", "BID.VN").
    - Otherwise, return symbol as is.

    Args:
        symbol (str): The stock symbol to convert to YF ticker format.

    Returns:
        str: The stock symbol as a Yahoo Finance ticker.

    Remarks:
        Currently support only AU/US/VN markets.
    """
    symbol = symbol.upper()
    if ":" in symbol:
        exchange, ticker = symbol.split(":", 1)
        if exchange == "ASX":
            return f"{ticker}.AX"
        elif exchange in ("HOSE", "HNX", "UPCOM"):
            return f"{ticker}.VN"
        elif exchange in ("NYSE", "NASDAQ"):
            return ticker
    return symbol


def number_to_human_format(num: int | float, precision: int = 2):
    """
    Convert a number into a human-readable format with K, M, B, T suffixes.

    Args:
        num (int|float): The number to format.
        precision (int): Decimal places to keep.

    Returns:
        str: Formatted string.
    """
    sign = "-" if num < 0 else ""
    num = abs(num)

    suffixes = ["", "K", "M", "B", "T"]
    idx = 0

    while num >= 1000 and idx < len(suffixes) - 1:
        num /= 1000.0
        idx += 1

    formatted = f"{num:.{precision}f}".rstrip("0").rstrip(".")
    return f"{sign}{formatted}{suffixes[idx]}"


def yyyymmdd_to_iso(yyyy_mm_dd: str, tz: ZoneInfo = None, tz_name: str = None) -> str | None:
    """
    Converts a date string in the format 'YYYY-MM-DD' to ISO format 'YYYY-MM-DD 00:00:00+hh:mm'.

    Args:
        yyyy_mm_dd (str): The date in the format YYYY-MM-DD
        tz (ZoneInfo, optional): The timezone to use. Defaults to None.
        tz_name (str, optional): The timezone name to use. Defaults to None.

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
