import json
import logging
import re
from datetime import UTC, date, datetime, time
from typing import Self
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from pydantic import Field, ValidationError, model_validator

from .. import config
from ..models import ai as models_ai
from ..models import events_listings as models_events_listings
from ..models import types as models_types
from ..services import crawler as services_crawler
from ..utils import ai_prompt as ai_prompt_utils
from ..utils import ai_reference as ai_reference_utils
from ..utils import cache, conv
from ..utils import data as data_utils
from . import ai_helper

_ASX_LISTINGS_CACHE_NAMESPACE = "asx-new-listings-analysis-v3"
_ASX_LISTINGS_EXTRACTION_CACHE_NAMESPACE = "asx-new-listings-extraction-v1"
_ASX_LISTINGS_RESEARCH_CACHE_NAMESPACE = "asx-new-listings-research-v1"
_ASX_LISTINGS_ASSESSMENT_CACHE_NAMESPACE = "asx-new-listings-assessment-v1"
_ASX_LISTINGS_EXTRACTION_CACHE_TTL = 24 * 60 * 60
_ASX_LISTINGS_EXTRACTION_PROMPT = "asx_new_listings_extraction.txt"
_ASX_LISTINGS_RESEARCH_PROMPT = "asx_new_listings_research.txt"
_ASX_LISTINGS_ASSESSMENT_PROMPT = "asx_new_listings_assessment.txt"
_ASX_LISTINGS_URL = "https://www.asx.com.au/listings/upcoming-floats-and-listings"
_ASX_COUNTRY = "AU"
_ASX_CURRENCY = "AUD"
_ASX_EXCHANGE = "ASX"
_ASX_LISTINGS_EXTRACT_TASK = "ASX_LISTTINGS_EXTRACT"
_ASX_LISTINGS_RESEARCH_TASK = "ASX_LISTTINGS_RESEARCH"
_ASX_LISTINGS_ANALYZE_TASK = "ASX_LISTTINGS_ANALYZE"
_ASX_UNDERWRITTEN_LISTINGS_RESEARCH_TASK = "ASX_LISTTINGS_UNDERWRITTEN_RESEARCH"
_ASX_UNDERWRITTEN_LISTINGS_ANALYZE_TASK = "ASX_LISTTINGS_UNDERWRITTEN_ANALYZE"
_ASX_SYMBOL_PATTERN = r"^ASX:[A-Z0-9]+$"
_ASX_SYMBOL_REGEX = re.compile(_ASX_SYMBOL_PATTERN)
_MAX_LISTINGS_TO_ANALYZE = 5
_RESEARCH_SECTION_NAMES = (
    "offer",
    "business",
    "financials",
    "valuation",
    "governance",
    "market_context",
    "risks_and_catalysts",
)
_SYDNEY_TZ = ZoneInfo("Australia/Sydney")
_INVALID_DATETIME = "1900-01-01 00:00:00+00:00"


class _ExtractedListingCandidate(models_ai.StrictAIModel):
    symbol: models_types.NonEmptyString
    company_name: models_types.NonEmptyString
    listing_date: date | None
    issue_price: float | None
    issue_type: str | None
    capital_to_raise: float | None
    is_underwritten: bool | None
    underwriters: list[str]
    lead_managers: list[str]
    principal_activities: str | None
    sector: str | None
    public_offer_close_date: date | None


class _ExtractedListingsResponse(models_ai.StrictAIModel):
    listings: list[_ExtractedListingCandidate]


class _ListingResearchSection(models_events_listings.ListingEvidenceSection):
    facts: list[models_events_listings.ListingEvidenceClaim] = Field(max_length=3)
    reference_ids: list[models_types.NonEmptyString]


class _ListingResearchSourceMetadata(models_ai.ReferenceSourceMetadata):
    id: models_types.NonEmptyString


class _ListingResearchResponse(models_ai.StrictAIModel):
    symbol: str = Field(pattern=_ASX_SYMBOL_PATTERN)
    as_of: datetime
    offer: _ListingResearchSection
    business: _ListingResearchSection
    financials: _ListingResearchSection
    valuation: _ListingResearchSection
    governance: _ListingResearchSection
    market_context: _ListingResearchSection
    risks_and_catalysts: _ListingResearchSection
    references: list[_ListingResearchSourceMetadata] = Field(min_length=1, max_length=5)


class _ListingResearchDraft(_ListingResearchResponse):
    @model_validator(mode="after")
    def validate_references(self) -> Self:
        ai_reference_utils.validate_reference_registry(self.references, self)
        return self


class _ListingResearch(_ListingResearchDraft):
    references: list[models_ai.ReferenceSource] = Field(min_length=1, max_length=5)


class _QuickListingRiskCatalystAnalysis(models_events_listings.ListingRiskCatalystAnalysis):
    risks: list[models_events_listings.ListingRisk] = Field(max_length=3)
    catalysts: list[models_events_listings.ListingCatalyst] = Field(max_length=3)


class _ListingAnalysisDraft(models_events_listings.ListingAnalysisBase):
    symbol: str = Field(pattern=_ASX_SYMBOL_PATTERN)
    risks_and_catalysts: _QuickListingRiskCatalystAnalysis


async def ai_get_asx_new_listings() -> list[models_events_listings.ListingEvent]:
    """
    Fetch, extract, and analyze up to five current or upcoming ASX listings.

    Listings before the current Sydney date are excluded. Today's listings are
    included, and results are ordered by the soonest confirmed listing date. Entries
    without a confirmed date or with supplied non-positive monetary values are
    excluded. Unavailable issue prices and capital amounts are retained as null.
    """
    today = _current_asx_date()
    events = _select_current_and_future_listings(
        await _get_asx_new_listings(),
        today=today,
    )
    events = events[:_MAX_LISTINGS_TO_ANALYZE]
    cache_key = _generate_analysis_cache_key(events, today=today)
    cached_events = await cache.get(cache_key)
    if cached_events is not None:
        return _validate_cached_events(cached_events)

    events = await _analyze_asx_listings(events)
    for event in events:
        event.date = conv.yyyymmdd_to_iso(event.date, _SYDNEY_TZ) or _INVALID_DATETIME
        event.timestamp = int(datetime.fromisoformat(event.date).timestamp())

    if all(event.analysis_status == "Completed" for event in events):
        await cache.set(
            cache_key,
            [event.model_dump(mode="json") for event in events],
            ttl=_analysis_cache_ttl(events, today=today),
        )
    return events


def _current_asx_date() -> date:
    return datetime.now(_SYDNEY_TZ).date()


def _select_current_and_future_listings(
    events: list[models_events_listings.ListingEvent],
    *,
    today: date,
) -> list[models_events_listings.ListingEvent]:
    return sorted(
        (event for event in events if datetime.fromisoformat(event.date).date() >= today),
        key=lambda event: (datetime.fromisoformat(event.date).date(), event.symbol),
    )


def _generate_analysis_cache_key(
    events: list[models_events_listings.ListingEvent],
    *,
    today: date,
) -> str:
    return cache.generate_hourly_key(
        _ASX_LISTINGS_CACHE_NAMESPACE,
        today.isoformat(),
        *(
            _task_cache_identity(task_id)
            for task_id in (
                _ASX_LISTINGS_EXTRACT_TASK,
                _ASX_LISTINGS_RESEARCH_TASK,
                _ASX_LISTINGS_ANALYZE_TASK,
                _ASX_UNDERWRITTEN_LISTINGS_RESEARCH_TASK,
                _ASX_UNDERWRITTEN_LISTINGS_ANALYZE_TASK,
            )
        ),
        *(_event_input_json(event) for event in events),
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
    days_until_listing = (datetime.fromisoformat(event.date).date() - today).days
    if days_until_listing <= 1:
        return 60 * 60
    if days_until_listing <= 7:
        return 6 * 60 * 60
    return 24 * 60 * 60


def _analysis_cache_ttl(
    events: list[models_events_listings.ListingEvent],
    *,
    today: date,
) -> int:
    return min((_listing_cache_ttl(event, today=today) for event in events), default=60 * 60)


def _validate_cached_events(cached_events: object) -> list[models_events_listings.ListingEvent]:
    if not isinstance(cached_events, list):
        raise RuntimeError("ASX listings analysis cache contains an invalid value")
    try:
        return [
            event.model_copy(deep=True)
            if isinstance(event, models_events_listings.ListingEvent)
            else models_events_listings.ListingEvent.model_validate(event)
            for event in cached_events
        ]
    except (TypeError, ValidationError) as exc:
        raise RuntimeError("ASX listings analysis cache contains an invalid value") from exc


async def _get_asx_new_listings() -> list[models_events_listings.ListingEvent]:
    html_content = await services_crawler.fetch_webpage_content(_ASX_LISTINGS_URL)
    if not html_content:
        raise RuntimeError("[ASX Listings] Failed to fetch the ASX upcoming-listings page.")

    soup = BeautifulSoup(html_content, "html.parser")
    listing_texts = [
        el.get_text(" ", strip=True) for el in soup.select("div.multi-column-height") if "Listing date" in el.get_text()
    ]
    if not listing_texts:
        return []

    sectors = ", ".join(data_utils.asx_sector_yf_static_tickers)
    raw_input = "\n========== LISTING ==========\n".join(listing_texts)
    extract_prompt = ai_prompt_utils.render_prompt(
        _ASX_LISTINGS_EXTRACTION_PROMPT,
        {
            "SECTORS": sectors,
            "RAW_INPUT": raw_input,
        },
    )

    cache_key = cache.generate_hourly_key(
        _ASX_LISTINGS_EXTRACTION_CACHE_NAMESPACE,
        extract_prompt,
        json.dumps(_ExtractedListingsResponse.model_json_schema(), sort_keys=True),
        _task_cache_identity(_ASX_LISTINGS_EXTRACT_TASK),
    )
    cached_extraction = await cache.get(cache_key)
    if cached_extraction is not None:
        try:
            extracted = (
                cached_extraction.model_copy(deep=True)
                if isinstance(cached_extraction, _ExtractedListingsResponse)
                else _ExtractedListingsResponse.model_validate(cached_extraction)
            )
        except (TypeError, ValidationError) as exc:
            raise RuntimeError("ASX listings extraction cache contains an invalid value") from exc
    else:
        extract_result = await ai_helper.ai_exec_task(
            _ASX_LISTINGS_EXTRACT_TASK,
            extract_prompt,
            country=_ASX_COUNTRY,
            response_json_schema=_ExtractedListingsResponse.model_json_schema(),
            schema_name="asx_listing_extraction",
        )
        if extract_result.is_error:
            raise RuntimeError(f"[ASX Listings] AI extraction failed: {extract_result.error_msg}")

        try:
            extracted = _ExtractedListingsResponse.model_validate_json(extract_result.completion)
        except ValidationError as exc:
            raise ValueError("[ASX Listings] AI extraction returned an invalid structured response.") from exc
        await cache.set(
            cache_key,
            extracted.model_dump(mode="json"),
            ttl=_ASX_LISTINGS_EXTRACTION_CACHE_TTL,
        )

    events: list[models_events_listings.ListingEvent] = []
    seen_symbols: set[str] = set()
    for candidate in extracted.listings:
        event = _validated_listing_event(candidate)
        if event is None or event.symbol in seen_symbols:
            continue
        seen_symbols.add(event.symbol)
        events.append(event)
    return events


def _validated_listing_event(
    candidate: _ExtractedListingCandidate,
) -> models_events_listings.ListingEvent | None:
    if candidate.listing_date is None:
        return None
    if candidate.issue_price is not None and candidate.issue_price <= 0:
        return None
    if candidate.capital_to_raise is not None and candidate.capital_to_raise <= 0:
        return None

    symbol = candidate.symbol.strip().upper()
    if not symbol.startswith(f"{_ASX_EXCHANGE}:"):
        symbol = f"{_ASX_EXCHANGE}:{symbol}"
    if _ASX_SYMBOL_REGEX.fullmatch(symbol) is None:
        logging.warning("[ASX Listings] Ignoring listing with invalid ASX symbol '%s'.", candidate.symbol)
        return None

    issue_type = candidate.issue_type.strip() if candidate.issue_type else None
    sector = candidate.sector.strip().upper() if candidate.sector else None
    if sector not in data_utils.asx_sector_yf_static_tickers:
        sector = None

    listing_at = datetime.combine(candidate.listing_date, time.min, tzinfo=_SYDNEY_TZ)
    try:
        return models_events_listings.ListingEvent(
            symbol=symbol,
            exchange=_ASX_EXCHANGE,
            company_name=candidate.company_name.strip(),
            timestamp=int(listing_at.timestamp()),
            date=candidate.listing_date.isoformat(),
            event_category="listing",
            source_name=_ASX_EXCHANGE,
            link=_ASX_LISTINGS_URL,
            issue_price=candidate.issue_price,
            issue_type=issue_type,
            sector=sector,
            principal_activities=candidate.principal_activities,
            currency=_ASX_CURRENCY,
            capital_to_raise=candidate.capital_to_raise,
            public_offer_close_date=(
                candidate.public_offer_close_date.isoformat() if candidate.public_offer_close_date else None
            ),
            is_underwritten=candidate.is_underwritten,
            underwriters=_clean_names(candidate.underwriters),
            lead_managers=_clean_names(candidate.lead_managers),
        )
    except ValidationError:
        logging.warning("[ASX Listings] Ignoring invalid extracted listing '%s'.", candidate.symbol)
        return None


def _clean_names(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value.strip() for value in values if value.strip()))


async def _analyze_asx_listings(
    events: list[models_events_listings.ListingEvent],
) -> list[models_events_listings.ListingEvent]:
    for event in events:
        try:
            research = await _research_asx_listing(event)
            event.analysis = await _assess_asx_listing(event, research)
            event.analysis_status = "Completed"
            event.analysis_error = None
        except Exception:
            logging.exception("[ASX Listings] Analysis failed for '%s'.", event.symbol)
            event.analysis = None
            event.analysis_status = "Failed"
            event.analysis_error = "AI listing analysis failed"
    return events


async def _research_asx_listing(
    event: models_events_listings.ListingEvent,
) -> _ListingResearch:
    task_id = _ASX_UNDERWRITTEN_LISTINGS_RESEARCH_TASK if event.is_underwritten is True else _ASX_LISTINGS_RESEARCH_TASK
    underwriting_instruction = (
        "- The listing is explicitly underwritten. Give additional scrutiny to the underwriters, commitment scope, "
        "material conditions or termination rights, fees, residual funding risk, and whether underwriting meaningfully "
        "reduces execution risk. Record unavailable terms in data_gaps."
        if event.is_underwritten is True
        else ""
    )
    event_json = event.model_dump_json(
        exclude={"analysis", "analysis_error", "analysis_status"},
        exclude_none=False,
    )
    research_prompt = ai_prompt_utils.render_prompt(
        _ASX_LISTINGS_RESEARCH_PROMPT,
        {
            "UNDERWRITING_INSTRUCTION": underwriting_instruction,
            "EVENT_JSON": event_json,
        },
    )

    today = _current_asx_date()
    cache_key = cache.generate_hourly_key(
        _ASX_LISTINGS_RESEARCH_CACHE_NAMESPACE,
        today.isoformat(),
        research_prompt,
        json.dumps(_ListingResearchDraft.model_json_schema(), sort_keys=True),
        _task_cache_identity(task_id),
    )
    cached_research = await cache.get(cache_key)
    if cached_research is not None:
        try:
            return (
                cached_research.model_copy(deep=True)
                if isinstance(cached_research, _ListingResearch)
                else _ListingResearch.model_validate(cached_research)
            )
        except (TypeError, ValidationError) as exc:
            raise RuntimeError("ASX listing research cache contains an invalid value") from exc

    research_result = await ai_helper.ai_exec_task(
        task_id,
        research_prompt,
        country=_ASX_COUNTRY,
        response_json_schema=_ListingResearchDraft.model_json_schema(),
        schema_name="asx_listing_research",
    )
    if research_result.is_error:
        raise RuntimeError(f"AI research failed: {research_result.error_msg}")

    try:
        response = _ListingResearchResponse.model_validate_json(research_result.completion)
        research = _repair_research_reference_links(response)
    except ValidationError as exc:
        raise ValueError("AI research returned an invalid structured response.") from exc
    if research.symbol != event.symbol:
        raise ValueError("AI research returned a different symbol.")

    finalized_research = _finalize_research_sources(
        research,
        research_result.citation_urls,
        accessed_at=datetime.now(UTC),
    )
    await cache.set(
        cache_key,
        finalized_research.model_dump(mode="json"),
        ttl=_listing_cache_ttl(event, today=today),
    )
    return finalized_research


def _repair_research_reference_links(
    research: _ListingResearchResponse,
) -> _ListingResearchDraft:
    research_data = research.model_dump()
    registry_ids = {reference.id for reference in research.references}
    missing_ids: set[str] = set()

    for section_name in _RESEARCH_SECTION_NAMES:
        section = research_data[section_name]
        section_missing_ids = set(section["reference_ids"]) - registry_ids
        missing_ids.update(section_missing_ids)
        section_orphan_ids = set(section_missing_ids)
        valid_section_ids = [reference_id for reference_id in section["reference_ids"] if reference_id in registry_ids]

        repaired_facts = []
        dropped_fact_count = 0
        for fact in section["facts"]:
            fact_missing_ids = set(fact["reference_ids"]) - registry_ids
            missing_ids.update(fact_missing_ids)
            section_orphan_ids.update(fact_missing_ids)
            valid_fact_ids = [reference_id for reference_id in fact["reference_ids"] if reference_id in registry_ids]
            if not valid_fact_ids:
                dropped_fact_count += 1
                continue
            fact["reference_ids"] = list(dict.fromkeys(valid_fact_ids))
            repaired_facts.append(fact)
            valid_section_ids.extend(valid_fact_ids)

        section["facts"] = repaired_facts
        section["reference_ids"] = list(dict.fromkeys(valid_section_ids))
        if section_orphan_ids or dropped_fact_count:
            missing_text = ", ".join(sorted(section_orphan_ids))
            repair_summary = f"Ignored missing source IDs: {missing_text}."
            if dropped_fact_count:
                repair_summary += f" Removed {dropped_fact_count} unsupported fact(s)."
            section["data_gaps"].append(repair_summary)

    used_reference_ids = ai_reference_utils.collect_reference_ids(research_data)
    research_data["references"] = [
        reference for reference in research_data["references"] if reference["id"] in used_reference_ids
    ]

    if missing_ids:
        logging.warning(
            "[ASX Listings] Ignored research links to missing source IDs: %s.",
            ", ".join(sorted(missing_ids)),
        )
    return _ListingResearchDraft.model_validate(research_data)


def _finalize_research_sources(
    research: _ListingResearchDraft,
    citation_urls: list[str],
    *,
    accessed_at: datetime,
) -> _ListingResearch:
    canonicalized = ai_reference_utils.canonicalize_reference_sources(
        research.references,
        citation_urls,
        accessed_at=accessed_at,
    )
    unverified_count = sum(not reference.is_verified for reference in canonicalized.references)
    if unverified_count:
        logging.warning(
            "[ASX Listings] %d of %d research sources could not be provider-verified.",
            unverified_count,
            len(canonicalized.references),
        )

    research_data = ai_reference_utils.remap_reference_ids(
        research,
        canonicalized.id_map,
    )
    if not isinstance(research_data, dict):
        raise TypeError("Remapped listing research must be an object.")
    research_data["as_of"] = accessed_at
    research_data["references"] = [reference.model_dump() for reference in canonicalized.references]
    return _ListingResearch.model_validate(research_data)


async def _assess_asx_listing(
    event: models_events_listings.ListingEvent,
    research: _ListingResearch,
) -> models_events_listings.ListingAnalysis:
    task_id = _ASX_UNDERWRITTEN_LISTINGS_ANALYZE_TASK if event.is_underwritten is True else _ASX_LISTINGS_ANALYZE_TASK
    underwriting_instruction = (
        "- The listing is explicitly underwritten. Assess the quality and limitations of that support, including "
        "conditions, termination exposure, underwriter quality, and residual execution risk. Do not treat "
        "underwriting as proof of investor demand or listing success."
        if event.is_underwritten is True
        else ""
    )
    today = _current_asx_date()
    listing_date = datetime.fromisoformat(event.date).date()
    expected_status = "Listed" if listing_date < today else "Upcoming"
    event_json = event.model_dump_json(
        exclude={"analysis", "analysis_error", "analysis_status"},
        exclude_none=False,
    )
    research_json = research.model_dump_json()
    analysis_prompt = ai_prompt_utils.render_prompt(
        _ASX_LISTINGS_ASSESSMENT_PROMPT,
        {
            "SYMBOL": event.symbol,
            "EXPECTED_STATUS": expected_status,
            "UNDERWRITING_INSTRUCTION": underwriting_instruction,
            "EVENT_JSON": event_json,
            "RESEARCH_JSON": research_json,
        },
    )

    cache_key = cache.generate_hourly_key(
        _ASX_LISTINGS_ASSESSMENT_CACHE_NAMESPACE,
        today.isoformat(),
        analysis_prompt,
        json.dumps(_ListingAnalysisDraft.model_json_schema(), sort_keys=True),
        _task_cache_identity(task_id),
    )
    cached_analysis = await cache.get(cache_key)
    if cached_analysis is not None:
        try:
            return (
                cached_analysis.model_copy(deep=True)
                if isinstance(cached_analysis, models_events_listings.ListingAnalysis)
                else models_events_listings.ListingAnalysis.model_validate(cached_analysis)
            )
        except (TypeError, ValidationError) as exc:
            raise RuntimeError("ASX listing assessment cache contains an invalid value") from exc

    analysis_result = await ai_helper.ai_exec_task(
        task_id,
        analysis_prompt,
        country=_ASX_COUNTRY,
        response_json_schema=_ListingAnalysisDraft.model_json_schema(),
        schema_name="asx_listing_analysis",
    )
    if analysis_result.is_error:
        raise RuntimeError(f"AI assessment failed: {analysis_result.error_msg}")

    try:
        draft = _ListingAnalysisDraft.model_validate_json(analysis_result.completion)
    except ValidationError as exc:
        raise ValueError("AI assessment returned an invalid structured response.") from exc
    if draft.symbol != event.symbol:
        raise ValueError("AI assessment returned a different symbol.")
    if draft.listing_status != expected_status:
        raise ValueError("AI assessment returned an invalid listing status.")

    used_reference_ids = draft.referenced_source_ids()
    references = [reference for reference in research.references if reference.id in used_reference_ids]
    analysis_data = draft.model_dump()
    analysis_data["references"] = [reference.model_dump() for reference in references]
    analysis = models_events_listings.ListingAnalysis.model_validate(analysis_data)
    await cache.set(
        cache_key,
        analysis.model_dump(mode="json"),
        ttl=_listing_cache_ttl(event, today=today),
    )
    return analysis
