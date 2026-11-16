from typing import Annotated, Literal

import pycountry
from pydantic import BeforeValidator, Field


def _normalize_country_code(value: object) -> object:
    if not isinstance(value, str):
        return value
    normalized = value.strip().upper()
    if (
        len(normalized) != 2
        or not normalized.isascii()
        or not normalized.isalpha()
        or pycountry.countries.get(alpha_2=normalized) is None
    ):
        raise ValueError("country must be an ISO 3166-1 alpha-2 code")
    return normalized


def _normalize_currency_code(value: object) -> object:
    if not isinstance(value, str):
        return value
    normalized = value.strip().upper()
    if len(normalized) != 3 or not normalized.isascii() or not normalized.isalpha():
        raise ValueError("currency must be a three-letter code")
    return normalized


NonEmptyString = Annotated[str, Field(min_length=1)]
CountryCode = Annotated[
    str,
    BeforeValidator(_normalize_country_code),
    Field(min_length=2, max_length=2),
]
CurrencyCode = Annotated[
    str,
    BeforeValidator(_normalize_currency_code),
    Field(min_length=3, max_length=3),
]
DataQuality = Literal["High", "Medium", "Low", "Insufficient"]

MarketCapType = Literal["Large", "Mid", "Small", "Micro", "Nano", None]
LARGE_CAP: MarketCapType = "Large"
MID_CAP: MarketCapType = "Mid"
SMALL_CAP: MarketCapType = "Small"
MICRO_CAP: MarketCapType = "Micro"
NANO_CAP: MarketCapType = "Nano"

AssetType = Literal["ETF", "MUTUAL FUND", "CRYPTO", "REIT", "LIC", "HYBRID", "STANDARD", "OTHER", None]
ETF_ASSET: AssetType = "ETF"
MUTUAL_FUND_ASSET: AssetType = "MUTUAL FUND"
CRYPTO_ASSET: AssetType = "CRYPTO"
REIT_ASSET: AssetType = "REIT"
LIC_ASSET: AssetType = "LIC"
HYBRID_ASSET: AssetType = "HYBRID"
STANDARD_ASSET: AssetType = "STANDARD"
OTHER_ASSET: AssetType = "OTHER"
