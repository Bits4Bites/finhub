from zoneinfo import ZoneInfo

import yfinance as yf

from ..models import types
from . import asset as asset_utils
from . import conv, data


def detect_asset_type(ticker: yf.Ticker | None) -> types.AssetType | None:
    """Classify a Yahoo Finance security for asset-specific workflows.

    Args:
        ticker: The Yahoo Finance ticker whose metadata describes the security.

    Returns:
        The supported asset category, ``OTHER`` for unrecognized metadata, or
        ``None`` when the ticker or its metadata is unavailable.

    Notes:
        Classification uses the provider's quote type, sector, industry, and
        issuer name.
    """
    if not ticker:
        return None

    info = ticker.info
    if not info:
        return None

    quote_type = info.get("quoteType", "")
    sector = info.get("sector", "")
    industry = info.get("industry", "")
    corp_name = info.get("longName", info.get("shortName", ""))
    return asset_utils.detect_asset_type(quote_type=quote_type, sector=sector, industry=industry, corp_name=corp_name)


def tz_from_yf_ticker(ticker: yf.Ticker | None) -> ZoneInfo:
    """Select the market timezone used to interpret a ticker's dates.

    Args:
        ticker: The Yahoo Finance ticker whose metadata identifies its exchange.

    Returns:
        Sydney time for ASX listings, Ho Chi Minh City time for HOSE and HNX
        listings, or New York time for other or unavailable exchanges.

    Notes:
        New York is the fallback because Yahoo metadata does not always provide
        a recognized exchange.
    """
    exchange = ""
    info = ticker.info if ticker else None
    if info:
        exchange = conv.normalize_exchange_code(info.get("fullExchangeName") or info.get("exchange", ""))

    tz_map = {
        "ASX": "Australia/Sydney",
        "HOSE": "Asia/Ho_Chi_Minh",
        "HNX": "Asia/Ho_Chi_Minh",
    }
    return ZoneInfo(tz_map.get(exchange, "America/New_York"))


def is_in_index(*, index: str, ticker: yf.Ticker | None) -> bool:
    """Check whether a Yahoo Finance ticker belongs to a loaded market index.

    Args:
        index: The market-index code, such as ``NASDAQ100`` or ``ASX200``.
        ticker: The Yahoo Finance ticker to check.

    Returns:
        ``True`` when the ticker's exchange-qualified symbol is an index
        constituent; otherwise ``False``.

    Raises:
        KeyError: If the requested index is not loaded.

    Notes:
        Index and symbol matching is case-insensitive.
    """
    symbol = conv.to_exch_symb_format(ticker=ticker) or ""
    return asset_utils.is_in_index(index=index, symbol=symbol)


def lookup_index_yf_static_symbol(*, ticker: yf.Ticker | None) -> str | None:
    """Select a broad-market Yahoo benchmark for a stock.

    Args:
        ticker: The Yahoo Finance ticker whose exchange and index memberships
            identify its benchmark.

    Returns:
        The static Yahoo symbol for the most specific supported benchmark, or
        ``None`` when the ticker has no usable symbol or its exchange is not
        supported.

    Raises:
        KeyError: If required index membership data is not loaded.

    Notes:
        ASX stocks use the most specific tracked ASX index, falling back to All
        Ordinaries. NASDAQ stocks use NASDAQ-100 or the NASDAQ Composite. NYSE
        stocks use the first matching S&P 500, 400, or 600 benchmark, falling
        back to the Dow Jones U.S. Total Stock Market index.
    """
    symbol = conv.to_exch_symb_format(ticker=ticker) or ""
    if not symbol:
        return None
    exchange = symbol.split(":")[0]

    if exchange == "ASX":
        for index in ("ASX20", "ASX50", "ASX100", "ASX200", "ASX300"):
            if asset_utils.is_in_index(index=index, symbol=symbol):
                return data.asx_index_yf_static_tickers[index]
        return data.asx_index_yf_static_tickers["ASX"]

    if exchange == "NASDAQ":
        return (
            data.us_index_yf_static_tickers["NASDAQ100"]
            if asset_utils.is_in_index(index="NASDAQ100", symbol=symbol)
            else data.us_index_yf_static_tickers["NASDAQ"]
        )

    if exchange == "NYSE":
        for index in ["SP500", "SP400", "SP600"]:
            if asset_utils.is_in_index(index=index, symbol=symbol):
                return data.us_index_yf_static_tickers[index]
        return data.us_index_yf_static_tickers["DOWJONES"]

    return None


def lookup_peer_yf_static_symbol(*, ticker: yf.Ticker | None) -> str | None:
    """Select a Yahoo sector or industry benchmark for peer comparison.

    Args:
        ticker: The Yahoo Finance ticker whose exchange, sector, and industry
            identify its peer group.

    Returns:
        The static Yahoo symbol of a matching sector or industry benchmark,
        which may be an index or an ETF, or ``None`` when no supported benchmark
        is available.

    Notes:
        ASX matching uses sector metadata. NASDAQ and NYSE matching prefers a
        specific industry benchmark before falling back to the sector benchmark.
        Metadata matching is case-insensitive.
    """
    info = ticker.info if ticker else None
    if not info:
        return None

    symbol = conv.to_exch_symb_format(ticker=ticker) or ""
    sector = (info.get("sector", "") or "").upper()
    industry = (info.get("industry", "") or "").upper()
    exchange = symbol.split(":")[0]

    if exchange == "ASX":
        if sector in data.asx_sector_yf_static_tickers:
            return data.asx_sector_yf_static_tickers[sector]

    if exchange in ("NASDAQ", "NYSE"):
        if sector in data.us_industry_yf_static_tickers and industry in data.us_industry_yf_static_tickers[sector]:
            return data.us_industry_yf_static_tickers[sector][industry]
        if sector in data.us_sector_yf_static_tickers:
            return data.us_sector_yf_static_tickers[sector]

    return None


def classify_market_cap(ticker: yf.Ticker | None) -> tuple[types.MarketCapType | None, str | None]:
    """Classify a Yahoo Finance stock by market-cap tier and index membership.

    Args:
        ticker: The Yahoo Finance ticker whose metadata provides its country,
            exchange, symbol, and market capitalization.

    Returns:
        The market-cap category and most relevant recognized index. Returns
        ``(None, None)`` when metadata or market capitalization is unavailable,
        or when the listing country is unsupported.

    Raises:
        KeyError: If required index membership data is not loaded.
        TypeError: If ``marketCap`` cannot be converted to an integer.
        ValueError: If ``marketCap`` is invalid or negative.

    Notes:
        Missing country metadata defaults to the United States. Australia and
        the United States use tier thresholds of 10 billion, 2 billion,
        300 million, and 50 million in local currency. Vietnam uses thresholds
        of 10 trillion, 1 trillion, 100 billion, and 10 billion VND. Values below
        the lowest threshold are Nano Cap. Recognized index membership can
        override the threshold tier, while some untracked Australian and
        Vietnamese listings are downgraded.
    """
    info = ticker.info if ticker else None
    if not info or info.get("marketCap") is None:
        return None, None

    country = conv.country_to_iso2(info.get("country") or info.get("region") or "US")
    exchange = info.get("fullExchangeName") or info.get("exchange") or ""
    exchange = conv.normalize_exchange_code(exchange)
    symbol = info.get("symbol") or ""
    if country != "US":
        symbol = symbol.split(".")[0]
    exchange_symbol = f"{exchange}:{symbol}"
    market_cap = int(info["marketCap"])
    if market_cap < 0:
        raise ValueError("marketCap must not be negative")

    return asset_utils.classify_market_cap(country=country, exchange_symbol=exchange_symbol, market_cap=market_cap)
