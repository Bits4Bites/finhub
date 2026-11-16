from ..models import types
from ..services import market as services_market


def detect_asset_type(
    *,
    quote_type: str | None = None,
    sector: str | None = None,
    industry: str | None = None,
    corp_name: str | None = None,
) -> types.AssetType:
    """Classify provider metadata into a supported financial asset category.

    Args:
        quote_type: The provider's broad security type.
        sector: The provider's business-sector description.
        industry: The provider's industry description.
        corp_name: The security or issuer name.

    Returns:
        The supported asset category, or ``OTHER`` when the supplied metadata
        does not identify a recognized category.

    Notes:
        Metadata matching is case-insensitive. ETF, mutual-fund, and
        cryptocurrency quote types map directly to those categories. Equities
        default to Standard; real-estate REITs, asset-management or investment
        companies, and note or hybrid issuers map to their corresponding equity
        subtypes. When those equity signals overlap, REIT takes precedence over
        listed investment company, which takes precedence over hybrid.
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
    """Check whether an exchange-qualified stock symbol belongs to an index.

    Args:
        index: The market-index code, such as ``ASX200`` or ``NASDAQ100``.
        symbol: The stock symbol in ``EXCHANGE:CODE`` format.

    Returns:
        ``True`` when the symbol is an index constituent; otherwise ``False``.

    Raises:
        KeyError: If the requested index is not loaded.

    Notes:
        Index codes and symbols are matched case-insensitively.
    """
    return symbol.upper() in services_market.market_indices.indices[index.upper()]


def classify_market_cap(
    *, country: str, exchange_symbol: str, market_cap: int
) -> tuple[types.MarketCapType | None, str | None]:
    """Classify a company's market-cap tier for its home market.

    Args:
        country: The listing country as a country name or ISO code.
        exchange_symbol: The stock symbol in ``EXCHANGE:CODE`` format.
        market_cap: The company's non-negative market capitalization in the
            home market's currency.

    Returns:
        The market-cap category and the most relevant recognized index containing
        the company. Unsupported countries return ``(None, None)``.

    Raises:
        KeyError: If required market-index data is not loaded.
        ValueError: If ``market_cap`` is negative.

    Notes:
        Australia and the United States use thresholds of 10 billion, 2 billion,
        300 million, and 50 million in local currency. Vietnam uses thresholds
        of 10 trillion, 1 trillion, 100 billion, and 10 billion VND. Values below
        the lowest threshold are Nano Cap. ASX 50, NASDAQ-100, and S&P 500
        membership sets Large Cap; S&P 400 sets Mid Cap; and S&P 600 sets Small
        Cap. ASX 100 promotes a threshold Mid or Small Cap by one tier, while an
        Australian stock outside ASX 300 demotes either tier by one level. VN30
        sets Large Cap, VN100 sets Mid Cap, and HNX30 promotes a threshold Small
        Cap to Mid Cap. Other HOSE or HNX listings demote threshold Large or Mid
        Caps by one level. If memberships overlap, S&P 600 takes precedence over
        S&P 400 and broad large-cap memberships, ASX 50 takes precedence over
        broader ASX memberships, and VN30 takes precedence over VN100.
    """
    if market_cap < 0:
        raise ValueError("market_cap must not be negative")

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

        if country == "AU" and market_index is None:
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

        if country == "AU" and market_index is None:
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
                market_index = "HNX30"
                if cap_size == types.SMALL_CAP:
                    cap_size = types.MID_CAP
            else:
                # down 1 level
                if cap_size == types.MID_CAP:
                    cap_size = types.SMALL_CAP
                elif cap_size == types.LARGE_CAP:
                    cap_size = types.MID_CAP

    return cap_size, market_index
