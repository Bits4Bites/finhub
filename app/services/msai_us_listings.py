import decimal
import json
import logging
import math
import re
import typing
import urllib.parse
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import bs4
import pandas as pd
import pydantic

from .. import config
from ..models import ai as models_ai
from ..models import events_listings as models_events_listings
from ..models import types as models_types
from ..services import crawler as services_crawler
from ..utils import ai_prompt as ai_prompt_utils
from ..utils import ai_reference as ai_reference_utils
from ..utils import cache, conv
from . import ai_helper

_US_LISTINGS_CACHE_NAMESPACE = "us-new-listings-analysis"
_US_LISTINGS_RESEARCH_CACHE_NAMESPACE = "us-new-listings-research"
_US_LISTINGS_RESEARCH_PROMPT = "us_new_listings_research.txt"
_US_LISTINGS_ASSESSMENT_PROMPT = "us_new_listings_assessment.txt"
_US_LISTINGS_URL = "https://stockanalysis.com/ipos/calendar/"
_US_COUNTRY = "US"
_US_CURRENCY = "USD"
_US_LISTINGS_RESEARCH_TASK = "US_LISTTINGS_RESEARCH"
_US_LISTINGS_ANALYZE_TASK = "US_LISTTINGS_ANALYZE"
_MAX_LISTINGS_TO_ANALYZE = 5
_US_SYMBOL_PATTERN = r"^(?:NASDAQ|NYSE|AMEX):[A-Z0-9]+(?:[.-][A-Z0-9]+)*$"
_PAGE_FIELDS = frozenset(
    {
        "Ticker Symbol",
        "Stock Exchange",
        "Exchange",
        "IPO Date",
        "IPO Price",
        "IPO Price Range",
        "Shares Offered",
        "Deal Size",
        "Market Cap",
        "Revenue (ttm)",
        "Net Income",
        "Shares Out",
        "Industry",
        "Sector",
        "Security Type",
        "CIK Code",
        "Reporting Currency",
    }
)
_FINANCIAL_METRICS = frozenset(
    {
        "Revenue",
        "Operating Income",
        "Net Income",
        "Cash & Investments",
        "Total Debt",
        "Operating Cash Flow",
        "Free Cash Flow",
    }
)
_RESEARCH_SECTION_NAMES = (
    "offer",
    "business",
    "financials",
    "valuation",
    "governance",
    "market_context",
    "risks_and_catalysts",
)
_OUTLOOK_PERIOD_NAMES = ("ipo_day", "first_week", "first_two_weeks", "first_month")
_NY_TZ = ZoneInfo("America/New_York")
_INVALID_DATETIME = "1900-01-01 00:00:00+00:00"


class _CalendarListing(models_events_listings.ListingEvent):
    _calendar_metrics: dict[str, str] = pydantic.PrivateAttr(default_factory=dict)


class _ListingDossier(models_ai.StrictAIModel):
    symbol: str
    overview_url: str
    business_description: str = ""
    industry: str = ""
    metrics: dict[str, str] = pydantic.Field(default_factory=dict)
    calendar_metrics: dict[str, str] = pydantic.Field(default_factory=dict)
    financial_metrics: list[str] = pydantic.Field(default_factory=list)
    financial_periods: list[str] = pydantic.Field(default_factory=list)
    filing_url: str | None = None
    filing_date: str | None = None
    filing_form: str | None = None
    filing_text: str = ""
    cik: str | None = None
    offering_type: typing.Literal["OperatingCompany", "Unsupported", "Unknown"] = "Unknown"
    is_active: bool = False
    sources: dict[str, str] = pydantic.Field(default_factory=dict)
    data_gaps: list[str] = pydantic.Field(default_factory=list)
    conflicts: list[str] = pydantic.Field(default_factory=list)
    page_count: int = 0


class _ListingResearchSection(models_events_listings.ListingEvidenceSection):
    facts: list[models_events_listings.ListingEvidenceClaim] = pydantic.Field(max_length=3)
    reference_ids: list[models_types.NonEmptyString]


class _ListingResearchSource(models_ai.ReferenceSourceMetadata):
    id: models_types.NonEmptyString


class _ListingResearchDraft(models_ai.StrictAIModel):
    symbol: str = pydantic.Field(pattern=_US_SYMBOL_PATTERN)
    as_of: datetime
    offer: _ListingResearchSection
    business: _ListingResearchSection
    financials: _ListingResearchSection
    valuation: _ListingResearchSection
    governance: _ListingResearchSection
    market_context: _ListingResearchSection
    risks_and_catalysts: _ListingResearchSection
    references: list[_ListingResearchSource] = pydantic.Field(min_length=1, max_length=5)

    @pydantic.model_validator(mode="after")
    def validate_references(self) -> typing.Self:
        ai_reference_utils.validate_reference_registry(self.references, self)
        return self


class _ListingResearch(_ListingResearchDraft):
    references: list[models_ai.ReferenceSource] = pydantic.Field(min_length=1, max_length=5)


class _ListingPeriodOutlook(models_events_listings.ListingPeriodOutlook):
    assessment_type: typing.Literal["Forecast"]
    direction: typing.Literal["Up", "Flat", "Down"]
    expected_price_min: float | None = pydantic.Field(gt=0, allow_inf_nan=False)
    expected_price_max: float | None = pydantic.Field(gt=0, allow_inf_nan=False)
    expected_return_min_pct: float | None = pydantic.Field(allow_inf_nan=False)
    expected_return_max_pct: float | None = pydantic.Field(allow_inf_nan=False)
    assumptions: list[models_types.NonEmptyString] = pydantic.Field(min_length=1)


class _PricedListingPeriodOutlook(_ListingPeriodOutlook):
    expected_price_min: float = pydantic.Field(gt=0, allow_inf_nan=False)
    expected_price_max: float = pydantic.Field(gt=0, allow_inf_nan=False)


class _ListingOutlook(models_events_listings.ListingOutlook):
    ipo_day: _ListingPeriodOutlook
    first_week: _ListingPeriodOutlook
    first_two_weeks: _ListingPeriodOutlook
    first_month: _ListingPeriodOutlook


class _PricedListingOutlook(_ListingOutlook):
    ipo_day: _PricedListingPeriodOutlook
    first_week: _PricedListingPeriodOutlook
    first_two_weeks: _PricedListingPeriodOutlook
    first_month: _PricedListingPeriodOutlook


class _ListingRiskCatalystAnalysis(models_events_listings.ListingRiskCatalystAnalysis):
    risks: list[models_events_listings.ListingRisk] = pydantic.Field(max_length=3)
    catalysts: list[models_events_listings.ListingCatalyst] = pydantic.Field(max_length=3)


class _ListingAnalysisDraft(models_events_listings.ListingAnalysisBase):
    symbol: str = pydantic.Field(pattern=_US_SYMBOL_PATTERN)
    listing_status: typing.Literal["Upcoming"]
    overall_stance: typing.Literal["Bullish", "Neutral", "Bearish"]
    risks_and_catalysts: _ListingRiskCatalystAnalysis
    outlook: _ListingOutlook


class _PricedListingAnalysisDraft(_ListingAnalysisDraft):
    outlook: _PricedListingOutlook


async def ai_get_us_new_listings() -> list[models_events_listings.ListingEvent]:
    """Return all current/upcoming US listings and analyze up to five crawl-ranked IPOs.

    Screening has no maximum lead time and invokes no AI. Unsupported offerings,
    unresolved evidence conflicts and unselected listings remain in the response as
    Skipped. Cached analyses are reused; failed selected attempts are not replaced.
    """
    today = _current_ny_date()
    events = _select_current_and_future_listings(
        await _get_us_new_listings(),
        today=today,
    )
    events = await _analyze_us_listings(events)
    for event in events:
        event.timestamp_str = conv.yyyymmdd_to_iso(event.timestamp_str, _NY_TZ) or _INVALID_DATETIME
        event.timestamp = int(datetime.fromisoformat(event.timestamp_str).timestamp())

    return events


def _current_ny_date() -> date:
    return datetime.now(_NY_TZ).date()


def _select_current_and_future_listings(
    events: list[models_events_listings.ListingEvent],
    *,
    today: date,
) -> list[models_events_listings.ListingEvent]:
    return sorted(
        (event for event in events if datetime.fromisoformat(event.timestamp_str).date() >= today),
        key=lambda event: (datetime.fromisoformat(event.timestamp_str).date(), event.symbol),
    )


def _event_input_json(event: models_events_listings.ListingEvent) -> str:
    return event.model_dump_json(
        exclude={"analysis", "analysis_error", "analysis_status", "timestamp"},
        exclude_none=False,
    )


def _task_cache_identity(task_id: str) -> str:
    task_config = config.settings_llm_task.tasks.get(task_id)
    if task_config is None:
        return task_id
    return json.dumps(
        {
            "task": task_id,
            "vendor": task_config.vendor,
            "tier": task_config.tier,
            "model": task_config.model,
            "reasoning_effort": task_config.reasoning_effort,
            "use_web_search": task_config.use_web_search,
            "max_tool_calls": task_config.max_tool_calls,
        },
        sort_keys=True,
    )


def _listing_cache_ttl(
    event: models_events_listings.ListingEvent,
    *,
    today: date,
) -> int:
    days_until_listing = (datetime.fromisoformat(event.timestamp_str).date() - today).days
    if days_until_listing <= 1:
        return 60 * 60
    if days_until_listing <= 7:
        return 6 * 60 * 60
    return 24 * 60 * 60


async def _get_us_new_listings() -> list[models_events_listings.ListingEvent]:
    """Extract confirmed listing events from the Stock Analysis IPO calendar."""
    url = _US_LISTINGS_URL
    html_content = await services_crawler.fetch_webpage_content_fallback_to_playwright(url, cache_ttl=60 * 60)
    if not html_content:
        raise RuntimeError("[US Listings] Failed to fetch the IPO calendar.")
    table_count = len(bs4.BeautifulSoup(html_content, "html.parser").select("table#main-table"))

    events: list[models_events_listings.ListingEvent] = []
    seen_symbols: set[str] = set()
    for index in range(table_count):
        frame = services_crawler.extract_data_table_from_html(
            html_content, table_attr_filter={"id": "main-table"}, filter_skip=index
        )
        for row in frame.to_dict(orient="records"):
            try:
                symbol = _listing_cell_text(row.get("Symbol")).upper()
                exchange = conv.normalize_exchange_code(_listing_cell_text(row.get("Exchange")))
                if not exchange or re.fullmatch(r"[A-Z0-9]+(?:[.-][A-Z0-9]+)*", symbol) is None:
                    continue
                listing_at = datetime.strptime(_listing_cell_text(row.get("IPO Date")), "%b %d, %Y").replace(
                    tzinfo=_NY_TZ
                )

                price_text = _listing_cell_text(row.get("Price Range"))
                prices = re.split(r"[-\u2013\u2014]", price_text) if price_text else []
                if len(prices) > 2 or any(not part.strip() for part in prices):
                    raise ValueError("Invalid issue-price range")
                issue_price = _parse_listing_amount(prices[0]) if prices else None
                issue_price_upper = _parse_listing_amount(prices[1]) if len(prices) == 2 else None
                if len(prices) == 2 and (issue_price is None or issue_price_upper is None):
                    raise ValueError("Incomplete issue-price range")

                event = _CalendarListing(
                    symbol=f"{exchange}:{symbol}",
                    exchange=exchange,
                    company_name=_listing_cell_text(row.get("Company Name")) or None,
                    timestamp=int(listing_at.timestamp()),
                    timestamp_str=listing_at.date().isoformat(),
                    event_category="listing",
                    source_name="Stock Analysis",
                    link=url,
                    issue_price=issue_price,
                    issue_price_upper=issue_price_upper,
                    currency=_US_CURRENCY,
                    capital_to_raise=_parse_listing_amount(row.get("Deal Size")),
                )
                event._calendar_metrics = {
                    name: _listing_cell_text(row.get(name)) for name in ("Shares Offered", "Market Cap", "Revenue")
                }
            except ValueError, decimal.DecimalException:
                logging.warning("[US Listings] Ignoring invalid listing '%s'.", row.get("Symbol"))
                continue
            if event.symbol in seen_symbols:
                continue
            seen_symbols.add(event.symbol)
            events.append(event)
    return events


def _listing_cell_text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text.upper() in {"-", "\u2013", "\u2014", "N/A"} else text


def _parse_listing_amount(value: object) -> decimal.Decimal | None:
    text = _listing_cell_text(value).upper().replace("$", "").replace(",", "")
    if not text or text in {"NA", "TBA", "TBC", "TBD"}:
        return None
    multipliers = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000, "T": 1_000_000_000_000}
    multiplier = multipliers.get(text[-1], 1)
    if text[-1] in multipliers:
        text = text[:-1].strip()
    amount = decimal.Decimal(text) * multiplier
    if not amount.is_finite():
        raise ValueError("Listing amounts must be finite")
    return amount


def _page_fields(soup: bs4.BeautifulSoup | bs4.Tag) -> dict[str, str]:
    fields: dict[str, str] = {}
    for row in soup.select("tr"):
        cells = row.find_all(["td", "th"], recursive=False)
        if len(cells) == 2 and cells[0].get_text(" ", strip=True) in _PAGE_FIELDS:
            fields[cells[0].get_text(" ", strip=True)] = cells[1].get_text(" ", strip=True)
    for text in soup.find_all(string=lambda value: value and value.strip() in _PAGE_FIELDS):
        label = text.parent
        if label.name in {"td", "th"}:
            continue
        value = label.find_next_sibling()
        if value is not None:
            fields.setdefault(text.strip(), value.get_text(" ", strip=True))
    return fields


def _business_description(soup: bs4.BeautifulSoup | bs4.Tag) -> str:
    heading = soup.find(
        ["h1", "h2", "h3"],
        string=re.compile(r"^(?:About\b|Company Description|Business Description)", re.IGNORECASE),
    )
    paragraph = heading.find_next("p") if heading else None
    return re.sub(r"\s*\[Read more\]\s*$", "", paragraph.get_text(" ", strip=True)).strip() if paragraph else ""


def _company_identity(value: str) -> str:
    value = re.sub(
        r"\b(?:incorporated|inc|limited|ltd|corporation|corp|plc|ag|holdings?)\b",
        "",
        value.casefold(),
    )
    return re.sub(r"[^a-z0-9]", "", value)


def _check_page_identity(
    event: models_events_listings.ListingEvent,
    soup: bs4.BeautifulSoup | bs4.Tag,
    fields: dict[str, str],
    dossier: _ListingDossier,
) -> None:
    code = event.symbol.split(":", 1)[1]
    ticker = fields.get("Ticker Symbol")
    heading = soup.find("h1")
    heading_text = heading.get_text(" ", strip=True) if heading else ""
    if ticker:
        identity_matches = ticker.upper() == code
    else:
        identity_matches = f"({code})" in soup.get_text(" ", strip=True)[:800]
    if not identity_matches:
        dossier.conflicts.append("Company page does not identify the calendar ticker.")
    if event.company_name and heading_text.endswith(f"({code})"):
        company_name = heading_text[: -len(f"({code})")].strip()
        if _company_identity(company_name) != _company_identity(event.company_name):
            dossier.conflicts.append("Company name differs between the calendar and company page.")
    page_exchange = fields.get("Stock Exchange") or fields.get("Exchange")
    if page_exchange and conv.normalize_exchange_code(page_exchange) != event.exchange:
        dossier.conflicts.append("Exchange differs between the calendar and company page.")
    if fields.get("IPO Date"):
        try:
            page_date = datetime.strptime(fields["IPO Date"], "%b %d, %Y").date()
        except ValueError:
            dossier.data_gaps.append("Company-page IPO date could not be parsed.")
        else:
            if page_date != datetime.fromisoformat(event.timestamp_str).date():
                dossier.conflicts.append("IPO date differs between the calendar and company page.")

    price_text = fields.get("IPO Price Range") or fields.get("IPO Price")
    if price_text and event.issue_price is not None:
        try:
            prices = [_parse_listing_amount(part) for part in re.split(r"[-\u2013\u2014]", price_text)]
        except ValueError, decimal.DecimalException:
            dossier.data_gaps.append("Company-page issue price could not be parsed.")
        else:
            expected = [event.issue_price]
            if event.issue_price_upper is not None:
                expected.append(event.issue_price_upper)
            if len(prices) != len(expected) or any(
                actual is None or not math.isclose(float(actual), quoted, abs_tol=0.005)
                for actual, quoted in zip(prices, expected)
            ):
                dossier.conflicts.append("Issue-price terms differ between the calendar and company page.")


def _sec_filing_url(url: str) -> tuple[str, str] | None:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc.lower() not in {"www.sec.gov", "sec.gov"}:
        return None
    path = parsed.path
    if path == "/ix":
        path = urllib.parse.parse_qs(parsed.query).get("doc", [""])[0]
    match = re.fullmatch(r"/Archives/edgar/data/(\d+)/\d+/[\w.-]+\.html?", path, re.IGNORECASE)
    if match is None:
        return None
    return ai_reference_utils.normalize_url(f"https://www.sec.gov{path}"), str(int(match[1]))


def _find_filing(soup: bs4.BeautifulSoup | bs4.Tag, dossier: _ListingDossier) -> None:
    issuer_ciks: set[str] = set()
    profile_cik = _page_fields(soup).get("CIK Code", "")
    if profile_cik.isdecimal():
        issuer_ciks.add(str(int(profile_cik)))
    filings: list[tuple[str, str, str | None, str | None]] = []
    for row in soup.select("tr"):
        cells = row.find_all("td", recursive=False)
        if len(cells) < 3:
            continue
        form = cells[1].get_text(" ", strip=True).upper()
        if form == "RW" and not filings:
            dossier.is_active = False
            dossier.data_gaps.append("The latest registration-related filing is a withdrawal request.")
            return
        if form not in {"S-1", "S-1/A", "F-1", "F-1/A", "424B4"}:
            continue
        link = cells[2].find("a", href=True)
        filing = _sec_filing_url(str(link["href"])) if link else None
        if filing:
            filings.append((*filing, cells[0].get_text(" ", strip=True), form))
    for link in soup.select("a[href]"):
        href = str(link["href"])
        parsed = urllib.parse.urlsplit(href)
        if parsed.scheme == "https" and parsed.netloc.lower() in {"www.sec.gov", "sec.gov"}:
            cik = urllib.parse.parse_qs(parsed.query).get("CIK", [""])[0]
            if cik.isdecimal():
                issuer_ciks.add(str(int(cik)))
        if re.search(r"\b(?:S-1|F-1|424B4)\b", link.get_text(" ", strip=True), re.IGNORECASE):
            filing = _sec_filing_url(href)
            if filing and not any(existing[0] == filing[0] for existing in filings):
                filings.append((*filing, None, None))
    if dossier.cik and issuer_ciks and dossier.cik not in issuer_ciks:
        dossier.conflicts.append("Issuer CIK differs between company pages.")
        return
    for filing_url, cik, filing_date, filing_form in filings:
        if issuer_ciks and cik not in issuer_ciks:
            dossier.conflicts.append("Registration-document CIK differs from the company data-source CIK.")
            continue
        dossier.filing_url = filing_url
        dossier.filing_date = filing_date
        dossier.filing_form = filing_form
        dossier.cik = cik
        return


def _classify_offering(dossier: _ListingDossier, fields: dict[str, str]) -> None:
    description = dossier.business_description.casefold()
    security_type = fields.get("Security Type", "").casefold()
    if (
        dossier.industry.casefold() in {"shell companies", "closed-end funds", "exchange traded funds"}
        or re.search(
            r"\b(?:blank[- ]check company|special purpose acquisition company|closed[- ]end fund)\b", description
        )
        or re.search(r"\b(?:units?|warrants?|preferred|direct listing|uplisting)\b", security_type)
    ):
        dossier.offering_type = "Unsupported"
    elif dossier.industry and dossier.business_description:
        dossier.offering_type = "OperatingCompany"


async def _load_dossier_page(
    url: str,
    dossier: _ListingDossier,
    *,
    ttl: int,
    regulatory: bool = False,
) -> bs4.BeautifulSoup | bs4.Tag | None:
    dossier.page_count += 1
    try:
        content = (
            await services_crawler.fetch_webpage_content(url, retries=1, cache_ttl=ttl)
            if regulatory
            else await services_crawler.fetch_webpage_content_fallback_to_playwright(url, cache_ttl=ttl)
        )
    except Exception:
        logging.exception("[US Listings] Could not crawl '%s'.", url)
        content = None
    if not content:
        dossier.data_gaps.append(f"Source could not be retrieved: {url}")
        return None
    soup = bs4.BeautifulSoup(content, "html.parser")
    main = soup.find("main") or soup.find("body") or soup
    for element in main.select('script, style, nav, footer, form, svg, [aria-hidden="true"]'):
        element.decompose()
    return main


def _read_financials(soup: bs4.BeautifulSoup | bs4.Tag, dossier: _ListingDossier, url: str) -> None:
    tables = []
    metrics: set[str] = set()
    periods: set[str] = set()
    for table in soup.select("table"):
        first_row = table.select_one("thead tr") or table.find("tr")
        headings = (
            [cell.get_text(" ", strip=True) for cell in first_row.find_all(["th", "td"], recursive=False)]
            if first_row
            else []
        )
        period_ending = []
        date_row = table.select_one("thead tr.date-row")
        if date_row is not None:
            for cell in date_row.find_all(["th", "td"], recursive=False)[1:]:
                spans = cell.find_all("span")
                period_ending.append(cell.get("title") or (spans[-1] if spans else cell).get_text(" ", strip=True))
        rows = []
        for row in table.select("tbody tr") or table.select("tr")[1:]:
            cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["th", "td"], recursive=False)]
            if len(cells) > 1 and cells[0] in _FINANCIAL_METRICS:
                values = cells[1 : len(headings)]
                if any(_listing_cell_text(value) for value in values):
                    metrics.add(cells[0])
                    periods.update(headings[1 : 1 + len(values)])
                    rows.append(cells[: len(headings)])
        if rows:
            tables.append({"columns": headings, "period_ending": period_ending, "rows": rows})
    dossier.financial_metrics = sorted(metrics)
    dossier.financial_periods = sorted(periods)
    text = soup.get_text(" ", strip=True)
    units = re.search(r"(?:Financials in|Millions|Billions|Thousands)[^.]{0,100}\.", text, re.IGNORECASE)
    if not units:
        dossier.data_gaps.append("Financial reporting currency and units were not identified; do not infer them.")
    if not metrics:
        dossier.data_gaps.append("Financial history was not available in the financial summary tables.")
    dossier.sources[url] = f"{units[0] if units else 'Units undisclosed.'}\n{json.dumps(tables)}"[:12_000]


async def _crawl_us_listing(
    event: models_events_listings.ListingEvent,
    *,
    today: date,
) -> _ListingDossier:
    code = event.symbol.split(":", 1)[1].lower()
    url = f"https://stockanalysis.com/stocks/{code}/"
    dossier = _ListingDossier(
        symbol=event.symbol,
        overview_url=url,
        calendar_metrics=event._calendar_metrics if isinstance(event, _CalendarListing) else {},
    )
    ttl = _listing_cache_ttl(event, today=today)
    overview = await _load_dossier_page(url, dossier, ttl=ttl)
    if overview is None:
        return dossier
    fields = _page_fields(overview)
    _check_page_identity(event, overview, fields, dossier)
    if dossier.conflicts:
        return dossier
    dossier.metrics = fields
    dossier.industry = fields.get("Industry", "")
    dossier.business_description = _business_description(overview)
    introductory_text = overview.get_text(" ", strip=True)[:800]
    dossier.is_active = bool(re.search(r"\b(?:will go public|estimated IPO date)\b", introductory_text, re.IGNORECASE))
    if re.search(
        r"\b(?:withdrawn|postponed|cancelled|canceled|direct listing|uplisting)\b", introductory_text, re.IGNORECASE
    ):
        dossier.is_active = False
    _find_filing(overview, dossier)
    _classify_offering(dossier, fields)
    dossier.sources[url] = overview.get_text("\n", strip=True)[:8_000]
    if dossier.offering_type == "Unsupported":
        return dossier

    profile_url = f"{url}company/"
    profile = await _load_dossier_page(profile_url, dossier, ttl=ttl)
    if profile is not None:
        profile_fields = _page_fields(profile)
        _check_page_identity(event, profile, profile_fields, dossier)
        dossier.industry = profile_fields.get("Industry") or dossier.industry
        dossier.business_description = _business_description(profile) or dossier.business_description
        dossier.metrics.update(profile_fields)
        _find_filing(profile, dossier)
        _classify_offering(dossier, {**fields, **profile_fields})
        dossier.sources[profile_url] = profile.get_text("\n", strip=True)[:8_000]
    if dossier.conflicts or dossier.offering_type == "Unsupported":
        return dossier

    financial_url = f"{url}financials/"
    financials = await _load_dossier_page(financial_url, dossier, ttl=ttl)
    if financials is not None:
        _check_page_identity(event, financials, _page_fields(financials), dossier)
        _read_financials(financials, dossier, financial_url)
    if dossier.filing_url:
        filing = await _load_dossier_page(dossier.filing_url, dossier, ttl=ttl, regulatory=True)
        if filing is not None:
            dossier.filing_text = filing.get_text(" ", strip=True)[:16_000]
            dossier.sources[dossier.filing_url] = dossier.filing_text
    else:
        dossier.data_gaps.append("No issuer-matched S-1/F-1 registration document or prospectus was linked.")
    if not dossier.is_active:
        dossier.data_gaps.append("The company page did not confirm an active upcoming IPO.")

    if not dossier.conflicts:
        event.industry = dossier.industry or None
        event.sector = dossier.metrics.get("Sector") or None
        event.principal_activities = dossier.business_description or None
        event.issue_type = dossier.metrics.get("Security Type") or event.issue_type
    return dossier


def _eligible_for_analysis(dossier: _ListingDossier) -> bool:
    financial_snapshot = any(
        _optional_amount(dossier.metrics.get(name)) is not None for name in ("Revenue (ttm)", "Net Income")
    )
    return (
        dossier.offering_type == "OperatingCompany"
        and dossier.is_active
        and not dossier.conflicts
        and dossier.filing_url is not None
        and bool(dossier.business_description)
        and (bool(dossier.financial_metrics) or financial_snapshot)
    )


def _optional_amount(value: object) -> float | None:
    try:
        amount = _parse_listing_amount(value)
        number = float(amount) if amount is not None else None
        return number if number is not None and math.isfinite(number) else None
    except ValueError, decimal.DecimalException:
        return None


def _candidate_sort_key(
    event: models_events_listings.ListingEvent,
    dossier: _ListingDossier,
    *,
    today: date,
) -> tuple[float, float, float, int, int, float, int, str]:
    quality = (
        sum(
            (
                bool(dossier.business_description),
                bool(dossier.financial_metrics),
                bool(dossier.filing_text),
                event.issue_price is not None and event.capital_to_raise is not None,
            )
        )
        / 4
    )
    reliability = (
        sum((bool(dossier.cik), bool(dossier.financial_periods), bool(dossier.industry), not dossier.data_gaps)) / 4
    )
    depth = min(len(dossier.financial_metrics) / len(_FINANCIAL_METRICS), 1)
    efficiency = max(0, 1 - len(dossier.data_gaps) / 5)
    score = 0.50 * quality + 0.20 * reliability + 0.15 * depth + 0.15 * efficiency
    deal_size = event.capital_to_raise or 0
    market_cap = _optional_amount(dossier.metrics.get("Market Cap") or dossier.calendar_metrics.get("Market Cap")) or 0
    return (
        -round(score, 2),
        -quality,
        -reliability,
        -int(deal_size >= 50_000_000),
        -deal_size,
        -market_cap,
        (datetime.fromisoformat(event.timestamp_str).date() - today).days,
        event.symbol,
    )


async def _analyze_us_listings(
    events: list[models_events_listings.ListingEvent],
) -> list[models_events_listings.ListingEvent]:
    today = _current_ny_date()
    candidates: list[tuple[models_events_listings.ListingEvent, _ListingDossier]] = []
    for event in events:
        event.analysis = None
        event.analysis_error = None
        event.analysis_status = "Skipped"
        try:
            dossier = await _crawl_us_listing(event, today=today)
            if _eligible_for_analysis(dossier):
                candidates.append((event, dossier))
            else:
                logging.info(
                    "[US Listings] Skipping '%s': type=%s, active=%s, conflicts=%s, gaps=%s.",
                    event.symbol,
                    dossier.offering_type,
                    dossier.is_active,
                    dossier.conflicts,
                    dossier.data_gaps,
                )
        except Exception:
            logging.exception("[US Listings] Screening failed for '%s'.", event.symbol)

    candidates.sort(key=lambda candidate: _candidate_sort_key(*candidate, today=today))
    for event, dossier in candidates[:_MAX_LISTINGS_TO_ANALYZE]:
        try:
            cache_key = _analysis_cache_key(event, dossier, today=today)
            cached_analysis = await cache.get(cache_key)
            if cached_analysis is not None:
                analysis = models_events_listings.ListingAnalysis.model_validate(cached_analysis)
                if analysis.symbol != event.symbol or analysis.listing_status != "Upcoming":
                    raise ValueError("Cached US listing analysis does not match the event.")
                event.analysis = analysis.model_copy(deep=True)
            else:
                research = await _research_us_listing(event, dossier, today=today)
                event.analysis = await _assess_us_listing(event, research, today=today)
                await cache.set(
                    cache_key,
                    event.analysis.model_dump(mode="json"),
                    ttl=_listing_cache_ttl(event, today=today),
                )
            event.analysis_status = "Completed"
        except Exception:
            logging.exception("[US Listings] Analysis failed for '%s'.", event.symbol)
            event.analysis = None
            event.analysis_status = "Failed"
            event.analysis_error = "AI listing analysis failed"
    return events


def _analysis_draft_model(
    event: models_events_listings.ListingEvent,
) -> type[_ListingAnalysisDraft]:
    return _PricedListingAnalysisDraft if event.issue_price is not None else _ListingAnalysisDraft


def _analysis_cache_key(
    event: models_events_listings.ListingEvent,
    dossier: _ListingDossier,
    *,
    today: date,
) -> str:
    return cache.generate_hourly_key(
        _US_LISTINGS_CACHE_NAMESPACE,
        today.isoformat(),
        config.settings_llm_task.tokenomics_mode,
        _event_input_json(event),
        dossier.model_dump_json(),
        ai_prompt_utils.load_prompt(_US_LISTINGS_RESEARCH_PROMPT),
        ai_prompt_utils.load_prompt(_US_LISTINGS_ASSESSMENT_PROMPT),
        json.dumps(_ListingResearchDraft.model_json_schema(), sort_keys=True),
        json.dumps(_analysis_draft_model(event).model_json_schema(), sort_keys=True),
        _task_cache_identity(_US_LISTINGS_RESEARCH_TASK),
        _task_cache_identity(_US_LISTINGS_ANALYZE_TASK),
    )


async def _research_us_listing(
    event: models_events_listings.ListingEvent,
    dossier: _ListingDossier,
    *,
    today: date,
) -> _ListingResearch:
    prompt = ai_prompt_utils.render_prompt(
        _US_LISTINGS_RESEARCH_PROMPT,
        {"EVENT_JSON": _event_input_json(event), "DOSSIER_JSON": dossier.model_dump_json()},
    )
    schema = _ListingResearchDraft.model_json_schema()
    cache_key = cache.generate_hourly_key(
        _US_LISTINGS_RESEARCH_CACHE_NAMESPACE,
        today.isoformat(),
        prompt,
        json.dumps(schema, sort_keys=True),
        _task_cache_identity(_US_LISTINGS_RESEARCH_TASK),
    )
    cached_research = await cache.get(cache_key)
    if cached_research is not None:
        research = _ListingResearch.model_validate(cached_research)
        if research.symbol != event.symbol:
            raise ValueError("Cached US listing research does not match the event.")
        return research.model_copy(deep=True)

    result = await ai_helper.ai_exec_task(
        _US_LISTINGS_RESEARCH_TASK,
        prompt,
        country=_US_COUNTRY,
        response_json_schema=schema,
        schema_name="us_listing_research",
    )
    if result.is_error:
        raise RuntimeError(f"AI research failed: {result.error_msg}")
    try:
        draft = _ListingResearchDraft.model_validate_json(result.completion)
    except pydantic.ValidationError as exc:
        ai_helper.log_structured_validation_failure("US Listings", "research", exc)
        raise ValueError("AI research returned invalid structured evidence.") from exc
    if draft.symbol != event.symbol:
        raise ValueError("AI research returned a different symbol.")
    accessed_at = datetime.now(UTC)
    canonicalized = ai_reference_utils.canonicalize_reference_sources(
        draft.references, result.citation_urls, accessed_at=accessed_at
    )
    data = ai_reference_utils.remap_reference_ids(draft, canonicalized.id_map)
    data["as_of"] = accessed_at
    data["references"] = [reference.model_dump() for reference in canonicalized.references]
    research = _ListingResearch.model_validate(data)
    await cache.set(cache_key, research.model_dump(mode="json"), ttl=_listing_cache_ttl(event, today=today))
    return research


def _assessment_context(
    event: models_events_listings.ListingEvent,
    research: _ListingResearch,
    *,
    today: date,
) -> dict[str, object]:
    return {
        "assessment_date": today.isoformat(),
        "listing_date": datetime.fromisoformat(event.timestamp_str).date().isoformat(),
        "currency": event.currency,
        "issue_price_anchor": event.issue_price,
        "issue_price_upper": event.issue_price_upper,
        "forecast_mode": "SubjectiveBaseCase" if event.issue_price is not None else "Qualitative",
        "sections_without_facts": [name for name in _RESEARCH_SECTION_NAMES if not getattr(research, name).facts],
        "unverified_source_count": sum(not reference.is_verified for reference in research.references),
        "return_basis": "Hypothetical IPO allocation at the offer-price anchor, not an aftermarket entry price.",
    }


async def _assess_us_listing(
    event: models_events_listings.ListingEvent,
    research: _ListingResearch,
    *,
    today: date,
) -> models_events_listings.ListingAnalysis:
    context = _assessment_context(event, research, today=today)
    prompt = ai_prompt_utils.render_prompt(
        _US_LISTINGS_ASSESSMENT_PROMPT,
        {
            "SYMBOL": event.symbol,
            "ASSESSMENT_CONTEXT_JSON": json.dumps(context),
            "EVENT_JSON": _event_input_json(event),
            "RESEARCH_JSON": research.model_dump_json(),
        },
    )
    draft_model = _analysis_draft_model(event)
    result = await ai_helper.ai_exec_task(
        _US_LISTINGS_ANALYZE_TASK,
        prompt,
        country=_US_COUNTRY,
        response_json_schema=draft_model.model_json_schema(),
        schema_name="us_listing_analysis",
    )
    if result.is_error:
        raise RuntimeError(f"AI assessment failed: {result.error_msg}")
    try:
        draft = draft_model.model_validate_json(result.completion)
    except pydantic.ValidationError as exc:
        ai_helper.log_structured_validation_failure("US Listings", "assessment", exc)
        raise ValueError("AI assessment returned an invalid structured response.") from exc
    if draft.symbol != event.symbol:
        raise ValueError("AI assessment returned a different symbol.")
    used_ids = draft.referenced_source_ids()
    references = [reference for reference in research.references if reference.id in used_ids]
    ai_reference_utils.validate_reference_registry(references, draft)

    data = draft.model_dump()
    data["as_of"] = datetime.now(UTC)
    data["references"] = [reference.model_dump() for reference in references]
    warnings = [
        "Subjective screening opinion, not a verified prediction or personalized investment recommendation.",
        "IPO allocations may be unavailable; offer-price returns are not returns from an aftermarket entry.",
    ]
    if context["unverified_source_count"]:
        warnings.append(
            f"{context['unverified_source_count']} source(s) lack provider citation verification; "
            "this does not disprove their contents."
        )
    if context["sections_without_facts"] or draft.overall_data_quality in {"Low", "Insufficient"}:
        warnings.append(
            "Evidence is incomplete; actual trading may differ materially from these conditional scenarios."
        )
    if event.issue_price is None:
        anchor_assumption = "No disclosed offer-price anchor; absolute prices and return ranges are unavailable."
    elif event.issue_price_upper is not None:
        anchor_assumption = (
            f"Uses the lower offer bound of {event.currency} {event.issue_price:g} from the disclosed "
            f"{event.issue_price:g}-{event.issue_price_upper:g} range; the final issue price may differ."
        )
    else:
        anchor_assumption = (
            f"Uses the offer price of {event.currency} {event.issue_price:g}, not an executable market price."
        )
    summary = data["executive_summary"]
    summary["summary"] = f"Subjective base-case view: {summary['summary']}"
    summary["assumptions"] = list(dict.fromkeys([*summary["assumptions"], anchor_assumption]))
    summary["data_gaps"] = list(dict.fromkeys([*summary["data_gaps"], *warnings]))
    for period_name in _OUTLOOK_PERIOD_NAMES:
        period = data["outlook"][period_name]
        period["rationale"] = f"Subjective base-case view: {period['rationale']}"
        period["assumptions"] = list(dict.fromkeys([*period["assumptions"], anchor_assumption]))
        period["data_gaps"] = list(dict.fromkeys([*period["data_gaps"], *warnings]))
        if event.issue_price is None:
            period["expected_price_min"] = None
            period["expected_price_max"] = None
            period["expected_return_min_pct"] = None
            period["expected_return_max_pct"] = None
        else:
            period["expected_return_min_pct"] = round((period["expected_price_min"] / event.issue_price - 1) * 100, 2)
            period["expected_return_max_pct"] = round((period["expected_price_max"] / event.issue_price - 1) * 100, 2)
    return models_events_listings.ListingAnalysis.model_validate(data)
