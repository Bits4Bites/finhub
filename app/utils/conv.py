from datetime import datetime
from zoneinfo import ZoneInfo

import babel.core
import babel.numbers
import pycountry
import yfinance as yf

_COUNTRY_ALIASES: dict[str, str] = {
    "uk": "GB",
    "u.k.": "GB",
    "great britain": "GB",
    "england": "GB",
    "u.s.": "US",
    "u.s.a.": "US",
    "uae": "AE",
    "u.a.e.": "AE",
    "republic of korea": "KR",
    "hong kong sar": "HK",
    "hong kong sar, china": "HK",
    "turkey": "TR",
}


def country_to_iso2(country: str | None) -> str:
    """Normalize a country identifier for market and financial-data workflows.

    Args:
        country: A country name, ISO country code, or supported market alias.

    Returns:
        The uppercase ISO 3166-1 alpha-2 code, or an empty string when the
        country is missing or unrecognized.

    Notes:
        Matching is case-insensitive and accepts common market aliases. Unknown
        names are not fuzzy-matched.
    """
    country = (country or "").strip()
    if not country:
        return ""
    try:
        return pycountry.countries.lookup(country).alpha_2
    except LookupError:
        return _COUNTRY_ALIASES.get(country.casefold(), "")


def country_to_currency_symbol(country: str | None) -> str:
    """Return the local display symbol for a country's active currency.

    Args:
        country: A country name, ISO country code, or supported market alias.

    Returns:
        The locale-appropriate currency symbol, or an empty string when the
        country or active currency cannot be determined.
    """
    country_code = country_to_iso2(country)
    currency_code = country_to_currency_code(country)
    if not country_code or not currency_code:
        return ""

    territory_languages = babel.core.get_global("territory_languages").get(country_code, {})
    language = max(
        territory_languages,
        key=lambda code: territory_languages[code].get("population_percent", 0),
        default="en",
    )
    locale = f"{language}_{country_code}"
    try:
        return babel.numbers.get_currency_symbol(currency_code, locale=locale)
    except babel.core.UnknownLocaleError:
        return babel.numbers.get_currency_symbol(currency_code, locale="en")


def country_to_currency_code(country: str | None) -> str:
    """Return the primary active currency code for a country.

    Args:
        country: A country name, ISO country code, or supported market alias.

    Returns:
        The ISO 4217 currency code, or an empty string when the country is
        unknown or has no active tender currency.
    """
    country_code = country_to_iso2(country)
    if not country_code:
        return ""

    currencies = babel.numbers.get_territory_currencies(country_code, tender=True)
    return currencies[0] if currencies else ""


# Mapping of known exchange name variants to canonical codes
_EXCHANGE_ALIASES: dict[str, str] = {
    "NMS": "NASDAQ",
    "NGM": "NASDAQ",
    "NCM": "NASDAQ",
    "NASDAQ": "NASDAQ",
    "NYQ": "NYSE",
    "NYSE": "NYSE",
    "NYS": "NYSE",
    "NYARCA": "NYSE",
    "NYSEARCA": "NYSE",
    "NYSE ARCA": "NYSE",
    "NEW YORK STOCK EXCHANGE": "NYSE",
    "BATS": "NYSE",
    "BTS": "NYSE",
    "CBOE BZX": "NYSE",
    "CBOE US": "NYSE",
}
_YF_SUFFIX_BY_EXCHANGE: dict[str, str] = {
    "ASX": "AX",
    "HNX": "VN",
    "HOSE": "VN",
    "LSE": "L",
    "UPCOM": "VN",
}


def normalize_exchange_code(exchange: str) -> str:
    """Normalize a provider exchange name or code for application use.

    Args:
        exchange: The exchange name or provider-specific exchange code.

    Returns:
        The canonical code for a recognized exchange. Unrecognized exchanges are
        returned trimmed and uppercased.
    """
    e = exchange.strip().upper()
    if e in _EXCHANGE_ALIASES:
        return _EXCHANGE_ALIASES[e]
    if "NASDAQ" in e:
        return "NASDAQ"
    if "NYSE" in e:
        return "NYSE"
    return e


def to_exch_symb_format(*, ticker: yf.Ticker | None = None, symbol: str | None = None) -> str:
    """Convert a stock identifier into the application's exchange-qualified form.

    Args:
        ticker: A Yahoo Finance ticker whose metadata identifies the exchange and
            provider symbol.
        symbol: A Yahoo Finance symbol or an existing ``EXCHANGE:CODE`` symbol.

    Returns:
        The uppercase ``EXCHANGE:CODE`` symbol. If the exchange cannot be
        determined, the normalized provider symbol is returned. An empty string
        is returned when no usable input is supplied.

    Notes:
        Supply either ``ticker`` or ``symbol``. When both are supplied, ticker
        metadata takes precedence.
    """
    normalized_symbol = (symbol or "").strip().upper()
    ticker_supplied = ticker is not None

    if ticker is None and not normalized_symbol:
        return ""

    if ticker is None and ":" in normalized_symbol:
        return normalized_symbol

    ticker = yf.Ticker(normalized_symbol) if ticker is None else ticker
    info = ticker.info or {}
    exchange = normalize_exchange_code(str(info.get("fullExchangeName") or info.get("exchange") or ""))
    provider_symbol = str(info.get("symbol") or "").strip().upper()
    if not provider_symbol and not ticker_supplied:
        provider_symbol = normalized_symbol
    if not provider_symbol:
        return ""

    # Non-US provider symbols use a market suffix; US dots can identify share classes such as BRK.B.
    if exchange and "." in provider_symbol and exchange not in {"NASDAQ", "NYSE"}:
        provider_symbol = provider_symbol.rsplit(".", 1)[0]
    return f"{exchange}:{provider_symbol}" if exchange else provider_symbol


def to_yf_symbol_format(symbol: str) -> str:
    """Convert an application stock symbol into Yahoo Finance format.

    Args:
        symbol: A Yahoo Finance symbol or an ``EXCHANGE:CODE`` symbol.

    Returns:
        The uppercase Yahoo Finance symbol. Unsupported exchanges are returned
        in normalized ``EXCHANGE:CODE`` form.

    Notes:
        Supported exchange mappings include ASX, HNX, HOSE, UPCOM, LSE, NASDAQ,
        and NYSE.
    """
    symbol = symbol.strip().upper()
    if ":" in symbol:
        exchange, ticker = symbol.split(":", 1)
        exchange = normalize_exchange_code(exchange)
        if exchange in ("NYSE", "NASDAQ"):
            return ticker
        suffix = _YF_SUFFIX_BY_EXCHANGE.get(exchange)
        if suffix:
            return f"{ticker}.{suffix}"
    return symbol


def number_to_human_format(num: int | float, precision: int = 2) -> str:
    """Format a financial value for compact human-readable display.

    Args:
        num: The numeric value to format.
        precision: The maximum number of decimal places to retain.

    Returns:
        The compact value using ``K``, ``M``, ``B``, or ``T`` where applicable.

    Raises:
        ValueError: If ``precision`` is negative.
    """
    if precision < 0:
        raise ValueError("precision must be non-negative")

    sign = "-" if num < 0 else ""
    num = abs(num)

    suffixes = ["", "K", "M", "B", "T"]
    idx = 0

    while num >= 1000 and idx < len(suffixes) - 1:
        num /= 1000.0
        idx += 1

    formatted = f"{num:.{precision}f}"
    if "." in formatted:
        formatted = formatted.rstrip("0").rstrip(".")
    return f"{sign}{formatted}{suffixes[idx]}"


def yyyymmdd_to_iso(yyyy_mm_dd: str, tz: ZoneInfo | None = None, tz_name: str | None = None) -> str | None:
    """Convert a calendar date into a timezone-aware midnight timestamp.

    Args:
        yyyy_mm_dd: The date in ``YYYY-MM-DD`` format.
        tz: The timezone to apply.
        tz_name: An IANA timezone name used when ``tz`` is not supplied.

    Returns:
        The ISO timestamp at midnight, or ``None`` when the date is invalid.

    Raises:
        ZoneInfoNotFoundError: If ``tz_name`` is not recognized.

    Notes:
        ``tz`` takes precedence over ``tz_name``. UTC is used when neither is
        supplied.
    """
    tz = tz or (ZoneInfo(tz_name) if tz_name else ZoneInfo("UTC"))
    try:
        return datetime.strptime(yyyy_mm_dd, "%Y-%m-%d").replace(tzinfo=tz).isoformat(sep=" ", timespec="seconds")
    except ValueError:
        return None
