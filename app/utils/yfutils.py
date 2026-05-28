from zoneinfo import ZoneInfo

import yfinance as yf

from ..models import types
from . import asset as asset_utils
from . import data


def detect_asset_type(ticker: yf.Ticker) -> types.AssetType:
    """
    Detects the asset type based on ticker info.

    Args:
        ticker (yf.Ticker): ticker info

    Returns:
        AssetType: asset type
    """
    if not ticker or not ticker.info:
        return None
    info = ticker.info
    quote_type = info.get("quoteType", "")
    sector = info.get("sector", "")
    industry = info.get("industry", "")
    corp_name = info.get("longName", info.get("shortName", ""))
    return asset_utils.detect_asset_type(quote_type=quote_type, sector=sector, industry=industry, corp_name=corp_name)


def tz_from_yf_ticker(ticker: yf.Ticker) -> ZoneInfo:
    """
    Gets the timezone for a Yahoo Finance ticker based on its exchange.

    Args:
        ticker (yf.Ticker): The Yahoo Finance ticker object.

    Returns:
        ZoneInfo: The timezone for the ticker's exchange. Defaults to America/New_York.
    """
    from . import conv

    exchange = ""
    if ticker and ticker.info:
        exchange = conv.normalize_exchange_code(ticker.info.get("fullExchangeName", ticker.info.get("exchange", "")))

    tz_map = {
        "ASX": "Australia/Sydney",
        "HOSE": "Asia/Ho_Chi_Minh",
        "HNX": "Asia/Ho_Chi_Minh",
    }
    return ZoneInfo(tz_map.get(exchange, "America/New_York"))


def is_in_index(*, index: str, ticker: yf.Ticker) -> bool:
    """
    Checks if a stock symbol in a market index.

    Args:
        index (str): The market index (e.g. "NASDAQ100", "ASX200", etc.).
        ticker (yf.Ticker): The stock ticker to check

    Returns:
        bool: True if the stock symbol in a market index, False otherwise.

    Remarks:
        Supply either ticker or symbol. If both are supplied, ticker takes precedence.
    """
    from . import conv

    symbol = conv.to_exch_symb_format(ticker=ticker) or ""
    return asset_utils.is_in_index(index=index, symbol=symbol)


def lookup_index_yf_static_symbol(*, ticker: yf.Ticker) -> str | None:
    """
    Look up the Yahoo Finance symbol of the market index that best represents
    the given stock's exchange and membership.

    For example:
        - CBA.AX (ASX member) → returns the YF symbol for ASX20 ("^ATLI")
        - AAPL (NASDAQ100 member) → returns the YF symbol for NASDAQ100 ("^NDX")
        - JPM (SP500 member on NYSE) → returns the YF symbol for SP500 ("^GSPC")

    Args:
        ticker (yf.Ticker): The stock ticker to find the representative index for.

    Returns:
        str | None: The Yahoo Finance symbol of the matching market index,
                    or None if the exchange is not recognized.

    Remarks:
        Currently, support only AU/US/VN markets.
    """
    from . import conv

    symbol = conv.to_exch_symb_format(ticker=ticker) or ""
    exchange = symbol.split(":")[0]

    if exchange == "ASX":
        for index in data.asx_index_yf_static_tickers.keys():
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


def lookup_peer_yf_static_symbol(*, ticker: yf.Ticker) -> str | None:
    """
    Look up the Yahoo Finance static symbol of a sector/industry ticker that serves as
    a peer benchmark for the given stock.

    For example:
        - CBA.AX (Financials sector) → returns the YF static symbol for the ASX Financials sector ("^AXFJ")
        - AAPL (Technology sector, Consumer Electronics industry) → returns the
          YF static symbol for the relevant US sector/industry ("^SP600-45202030")

    Args:
        ticker (yf.Ticker): The stock ticker to find the peer benchmark for.

    Returns:
        str | None: The Yahoo Finance symbol of the matching sector/industry ETF,
                    or None if no match is found.

    Remarks:
        Currently, support only AU/US markets.
    """
    from . import conv

    symbol = conv.to_exch_symb_format(ticker=ticker) or ""
    sector = (ticker.info.get("sector", "") or "").upper()
    industry = (ticker.info.get("industry", "") or "").upper()
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


def classify_market_cap(ticker: yf.Ticker) -> tuple[types.MarketCapType | None, str | None]:
    """
    Classifies a stock's market capitalization size and identifies its market index.

    Args:
        ticker (yf.Ticker): The stock ticker to classify.

    Returns:
        tuple[MarketCapType | None, str | None]: The classified market cap size
            and the market index the stock belongs to (if any).
    """
    from . import conv

    info = ticker.info if ticker else {}
    country = conv.country_to_iso2(info.get("country", info.get("region", "US")))
    exchange = info.get("fullExchangeName", info.get("exchange", "")) or ""
    exchange = conv.normalize_exchange_code(exchange)
    symbol = info.get("symbol", "")
    if country != "US":
        symbol = symbol.split(".")[0]
    exchange_symbol = f"{exchange}:{symbol}"
    market_cap = int(info.get("marketCap", 0))

    return asset_utils.classify_market_cap(country=country, exchange_symbol=exchange_symbol, market_cap=market_cap)
