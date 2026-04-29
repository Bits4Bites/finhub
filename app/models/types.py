from typing import Literal

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
