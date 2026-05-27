from .. import config
from ..models.types import (
    CRYPTO_ASSET,
    ETF_ASSET,
    HYBRID_ASSET,
    LIC_ASSET,
    MUTUAL_FUND_ASSET,
    OTHER_ASSET,
    REIT_ASSET,
    STANDARD_ASSET,
    AssetType,
)


def detect_asset_type(
    *, quote_type: str = None, sector: str = None, industry: str = None, corp_name: str = None
) -> AssetType:
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
            return ETF_ASSET
        case "MUTUALFUND":
            return MUTUAL_FUND_ASSET
        case "CRYPTOCURRENCY":
            return CRYPTO_ASSET
        case "EQUITY":
            asset_type = STANDARD_ASSET
            if sector == "REAL ESTATE" and "REIT" in industry:
                asset_type = REIT_ASSET
            elif "ASSET MANAGEMENT" in industry or "INVESTMENT" in corp_name:
                asset_type = LIC_ASSET
            elif "NOTE" in corp_name or "HYBRID" in corp_name:
                asset_type = HYBRID_ASSET
            return asset_type

    return OTHER_ASSET


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
