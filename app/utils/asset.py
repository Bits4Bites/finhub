from .. import config
from ..models import types


def detect_asset_type(
    *, quote_type: str = None, sector: str = None, industry: str = None, corp_name: str = None
) -> types.AssetType:
    """
    Detects the asset type based on ticker info (quote_type, sector, industry, and corporate name).

    Args:
        quote_type (string): quote type string obtained from YF info object
        sector (str): sector info obtained from YF info object
        industry (str): industry info obtained from YF info object
        corp_name (str): company name obtained from YF info object

    Returns:
        AssetType: asset type
    """
    quote_type = (quote_type or "").upper()
    sector = (sector or "").upper()
    industry = (industry or "").upper()
    corp_name = (corp_name or "").upper()

    match quote_type:
        case "ETF":
            return types.ETF_ASSET
        case "MUTUALFUND":
            return types.MUTUAL_FUND_ASSET
        case "CRYPTOCURRENCY":
            return types.CRYPTO_ASSET
        case "EQUITY":
            asset_type = types.STANDARD_ASSET
            if sector == "REAL ESTATE" and "REIT" in industry:
                asset_type = types.REIT_ASSET
            elif "ASSET MANAGEMENT" in industry or "INVESTMENT" in corp_name:
                asset_type = types.LIC_ASSET
            elif "NOTE" in corp_name or "HYBRID" in corp_name:
                asset_type = types.HYBRID_ASSET
            return asset_type

    return types.OTHER_ASSET


def is_in_index(*, index: str, symbol: str) -> bool:
    """
    Checks if a stock symbol in a market index.

    Args:
        index (str): The market index.
        symbol (str): The stock symbol to check, must be in format EXCHANGE:CODE.

    Returns:
        bool: True if the stock symbol in a market index, False otherwise.
    """
    return symbol.upper() in config.market_indices.indices[index.upper()]


def classify_market_cap(
    *, country: str, exchange_symbol: str, market_cap: int
) -> tuple[types.MarketCapType | None, str | None]:
    """
    Classifies a stock market capital.

    Args:
        country (str): The country to classify.
        exchange_symbol (str): The ticker classify (in format EXCHANGE:CODE).
        market_cap (int): The ticker's market cap value.

    Returns:
        tuple[models.MarketCapType|None, str|None]: classified market cap and (optional) index (e.g. "NASDAQ100")
    """
    cap_size: types.MarketCapType = None
    market_index = None

    from . import conv

    country = conv.country_to_iso2(country)
    exchange_symbol = conv.to_exch_symb_format(symbol=exchange_symbol)

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
