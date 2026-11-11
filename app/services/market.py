import json
import logging
from pathlib import Path

from ..utils.conv import country_to_iso2
from ..models import market as models_market

_INDEX_FILES = (
    ("ASX20", "asx20.json"),
    ("ASX50", "asx50.json"),
    ("ASX100", "asx100.json"),
    ("ASX200", "asx200.json"),
    ("ASX300", "asx300.json"),
    ("NASDAQ100", "nasdaq100.json"),
    ("SP500", "sp500.json"),
    ("SP400", "spmidcap400.json"),
    ("SP600", "spsmallcap600.json"),
    ("HNX30", "hnx30.json"),
    ("VN30", "vn30.json"),
    ("VN100", "vn100.json"),
)


class MarketIndexStore:
    """Process-local store for preloaded market-index data."""

    def __init__(self) -> None:
        # mapping {index -> {exchange:code -> CompanyBriefInfo}}
        self.indices: dict[str, dict[str, models_market.CompanyBriefInfo]] = {}
        # mapping {index -> raw json content}
        self.raw_json: dict[str, str] = {}
        # mapping {country -> {code -> CompanyBriefInfo}} for reverse lookup of company info from country and code
        self.company_revert_mappings: dict[str, dict[str, models_market.CompanyBriefInfo]] = {}

    def load(self, index: str, json_content: str) -> None:
        normalized_index = index.upper()
        index_data = json.loads(json_content)
        companies: dict[str, models_market.CompanyBriefInfo] = {}
        for entry in index_data["data"]:
            symbol = entry["symbol"].upper()
            companies[symbol] = models_market.CompanyBriefInfo(
                symbol=symbol,
                name=entry.get("company", symbol),
                sector=entry.get("sector", symbol),
                market_cap=int(entry.get("market_cap", 0)),
            )
        self.raw_json[normalized_index] = json_content
        self.indices[normalized_index] = companies

    def revert_lookup_company(self, country: str, code: str) -> models_market.CompanyBriefInfo | None:
        """Reverse lookup of company info from country and code.

        Args:
            country: The country code (e.g., "AU", "US") or name (e.g., "Australia", "United States").
            code: The company code (e.g., "BHP", "AAPL").

        Returns:
            The CompanyBriefInfo if found, otherwise None.
        """
        normalized_country = country_to_iso2(country)
        normalized_code = code.upper()
        return self.company_revert_mappings.get(normalized_country, {}).get(normalized_code)


market_indices = MarketIndexStore()


def load_default_indices() -> None:
    indices_dir = Path(__file__).resolve().parents[2] / "resources" / "indices"
    for index, filename in _INDEX_FILES:
        file_path = indices_dir / filename
        logging.info("Loading index '%s' data from file '%s'...", index, file_path)
        try:
            json_content = file_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            logging.error("Market-index file '%s' was not found.", file_path)
            continue
        except PermissionError:
            logging.error("Permission denied while reading market-index file '%s'.", file_path)
            continue
        except OSError:
            logging.exception("Failed to read market-index file '%s'.", file_path)
            continue
        if not json_content:
            logging.error("Market-index file '%s' is empty.", file_path)
            continue
        market_indices.load(index, json_content)


load_default_indices()
