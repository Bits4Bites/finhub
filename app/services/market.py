import json
import logging
from pathlib import Path

from ..models import market as models_market
from ..utils import conv

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
    """Store loaded market-index documents and constituent profiles.

    A new store is empty. Call :meth:`load` to add or replace an index before
    performing reverse company lookups. Index identifiers, company symbols,
    country inputs, and lookup codes are matched case-insensitively.
    """

    def __init__(self) -> None:
        """Create an empty process-local market-index store."""
        # mapping {index -> {exchange:code -> CompanyBriefInfo}}
        self.indices: dict[str, dict[str, models_market.CompanyBriefInfo]] = {}
        # mapping {index -> raw json content}
        self.raw_json: dict[str, str] = {}
        # mapping {country -> {code -> CompanyBriefInfo}} for reverse lookup of company info from country and code
        self.company_revert_mappings: dict[str, dict[str, models_market.CompanyBriefInfo]] = {}

    def load(self, index: str, json_content: str) -> None:
        """Load or replace one market index from its JSON document.

        Args:
            index: Case-insensitive index identifier. ``ASX`` prefixes map
                constituents to Australia, ``VN`` and ``HNX`` prefixes map to
                Vietnam, and all other identifiers map to the United States.
            json_content: JSON object containing a ``data`` array. Each entry
                requires ``symbol`` and may provide ``company``, ``sector``,
                and ``market_cap``. Company and sector default to the
                normalized symbol, while market capitalization defaults to
                zero.

        Returns:
            ``None``. Loaded constituents become available through
            :meth:`revert_lookup_company`. The exact document becomes
            available to the market-index HTTP endpoint only when this store
            is the module-global ``market_indices`` instance used by the
            router.

        Raises:
            json.JSONDecodeError: If ``json_content`` is not valid JSON.
            KeyError: If the document omits ``data`` or an entry omits
                ``symbol``.
            TypeError: If the document shape cannot be traversed as described.
            ValueError: If a constituent field cannot be converted to its
                documented model type.

        Notes:
            Reloading an index replaces its previous constituents and rebuilds
            reverse lookups for the affected country while retaining other
            loaded indexes.
        """
        normalized_index = index.upper()
        index_data = json.loads(json_content)
        companies: dict[str, models_market.CompanyBriefInfo] = {}
        country = (
            "AU"
            if normalized_index.startswith("ASX")
            else "VN"
            if normalized_index.startswith("VN") or normalized_index.startswith("HNX")
            else "US"
        )
        for entry in index_data["data"]:
            symbol = entry["symbol"].upper()
            company = models_market.CompanyBriefInfo(
                symbol=symbol,
                name=entry.get("company", symbol),
                sector=entry.get("sector", symbol),
                market_cap=int(entry.get("market_cap", 0)),
                country=country,
            )
            companies[symbol] = company
        self.raw_json[normalized_index] = json_content
        self.indices[normalized_index] = companies
        self.company_revert_mappings[country] = {
            company.extract_exchange_code()[1]: company
            for index_companies in self.indices.values()
            for company in index_companies.values()
            if company.country == country
        }

    def revert_lookup_company(self, country: str, code: str) -> models_market.CompanyBriefInfo | None:
        """Look up a loaded constituent by country and security code.

        Args:
            country: A supported country code, country name, or market alias.
            code: Company code without an exchange prefix.

        Returns:
            The matching company profile, or ``None`` when the country is
            unrecognized or the code is not loaded.
        """
        normalized_country = conv.country_to_iso2(country)
        normalized_code = code.upper()
        return self.company_revert_mappings.get(normalized_country, {}).get(normalized_code)


market_indices = MarketIndexStore()


def load_default_indices() -> None:
    """Load the bundled market-index datasets into the process-local store.

    Returns:
        ``None``. Successfully parsed datasets update ``market_indices``.

    Notes:
        The loader reads the fixed files under ``resources\\indices``. Missing,
        unreadable, or empty files are logged and skipped so other indexes can
        still load. Invalid JSON or invalid company records are not suppressed
        and propagate to the caller. Repeated calls refresh data for indexes
        that load successfully.
    """
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
