"""Documentation-driven black-box tests for ASX listing analysis."""

import asyncio
import copy
import json
from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch
from zoneinfo import ZoneInfo

import pytest

from app.services import ai_helper
from app.services import msai_asx_listings as service
from app.utils import ai_reference
from tests import ai_service_fixtures

_SYDNEY_TZ = ZoneInfo("Australia/Sydney")


def _today() -> date:
    return datetime.now(_SYDNEY_TZ).date()


def _calendar_html() -> str:
    return """
    <html>
      <div class="multi-column-height">
        Example issuer. Listing date and offer details are available.
      </div>
    </html>
    """


def _canonical_symbol(symbol: str) -> str:
    symbol = symbol.strip().upper()
    return symbol if symbol.startswith("ASX:") else f"ASX:{symbol}"


def _source_url(symbol: str) -> str:
    return f"https://www.asx.com.au/markets/company/{symbol.split(':', 1)[1]}"


def _candidate(
    symbol: str,
    listing_date: date | None,
    **overrides,
) -> dict[str, object]:
    data: dict[str, object] = {
        "symbol": symbol,
        "company_name": f"{symbol} Limited",
        "listing_date": listing_date.isoformat() if listing_date else None,
        "issue_price": 1.5,
        "issue_price_upper": None,
        "issue_type": "Ordinary fully paid shares",
        "capital_to_raise": 10_000_000,
        "is_underwritten": False,
        "underwriters": [],
        "lead_managers": ["Example Capital"],
        "principal_activities": "Technology services",
        "sector": "TECHNOLOGY",
        "public_offer_close_date": None,
    }
    data.update(overrides)
    return data


def _extraction_response(
    candidates: list[dict[str, object]],
) -> ai_helper.LLMResponse:
    return ai_helper.LLMResponse(completion=json.dumps({"listings": candidates}))


def _research_payload(symbol: str) -> dict[str, object]:
    source_url = _source_url(symbol)
    section = {
        "facts": [
            {
                "text": "The issuer disclosed its offer and business activities.",
                "reference_ids": [source_url],
            }
        ],
        "data_gaps": [],
        "reference_ids": [source_url],
    }
    return {
        "symbol": symbol,
        "as_of": datetime.now(UTC).isoformat(),
        "offer": copy.deepcopy(section),
        "business": copy.deepcopy(section),
        "financials": copy.deepcopy(section),
        "valuation": copy.deepcopy(section),
        "governance": copy.deepcopy(section),
        "market_context": copy.deepcopy(section),
        "risks_and_catalysts": copy.deepcopy(section),
        "references": [
            {
                "id": source_url,
                "title": "ASX listing information",
                "publisher": "ASX",
                "source_type": "Exchange",
                "published_at": None,
                "accessed_at": datetime.now(UTC).isoformat(),
                "url": source_url,
            }
        ],
    }


def _research_response(
    symbol: str,
    *,
    verified: bool = True,
) -> ai_helper.LLMResponse:
    return ai_helper.LLMResponse(
        completion=json.dumps(_research_payload(symbol)),
        citation_urls=[_source_url(symbol)] if verified else [],
    )


def _analysis_section(source_id: str) -> dict[str, object]:
    return {
        "summary": "Evidence-based assessment.",
        "data_quality": "High",
        "facts": [
            {
                "text": "The issuer disclosed its offer and business activities.",
                "reference_ids": [source_id],
            }
        ],
        "assumptions": [],
        "data_gaps": [],
        "reference_ids": [source_id],
    }


def _analysis_payload(symbol: str, listing_date: date) -> dict[str, object]:
    source_id = ai_reference.generate_source_id(_source_url(symbol))
    section = _analysis_section(source_id)
    period = {
        "assessment_type": "Forecast",
        "period_end": listing_date.isoformat(),
        "direction": "Flat",
        "expected_price_min": 1.4,
        "expected_price_max": 1.7,
        "expected_return_min_pct": None,
        "expected_return_max_pct": None,
        "confidence": 55,
        "rationale": "A conditional trading scenario.",
        "key_drivers": ["Offer execution"],
        "risk_factors": ["Market volatility"],
        "assumptions": ["The listing proceeds as announced."],
        "data_gaps": [],
        "reference_ids": [source_id],
    }
    return {
        "symbol": symbol,
        "as_of": datetime.now(UTC).isoformat(),
        "listing_status": "Upcoming",
        "overall_data_quality": "High",
        "executive_summary": copy.deepcopy(section),
        "overall_stance": "Neutral",
        "overall_confidence": 55,
        "offer": {
            **copy.deepcopy(section),
            "issue_price_assessment": "The offer price is a scenario anchor.",
            "capital_raise_assessment": "Gross proceeds support the stated plan.",
            "underwriting_assessment": "Underwriting support is disclosed.",
            "use_of_funds": ["Business expansion"],
            "dilution_and_escrow": None,
        },
        "business": {
            **copy.deepcopy(section),
            "business_model": "Technology services.",
            "revenue_sources": ["Service contracts"],
            "competitive_position": "Emerging participant.",
            "sector_context": "Competitive market.",
        },
        "financials": {
            **copy.deepcopy(section),
            "historical_performance": "Limited public history.",
            "profitability_and_cash_flow": "Offer documents provide limited detail.",
            "balance_sheet_and_funding": "The offer is intended to fund growth.",
            "forecast_quality": "Forecast evidence is limited.",
        },
        "valuation": {
            **copy.deepcopy(section),
            "valuation_view": "Sensitive to execution.",
            "implied_market_cap": None,
            "peer_comparison": "No verified peer multiple was supplied.",
            "sensitivity": "Depends on growth and market conditions.",
        },
        "governance": {
            **copy.deepcopy(section),
            "board_and_management": "Relevant experience is disclosed.",
            "ownership_and_escrow": "Terms remain subject to offer documents.",
            "governance_concerns": [],
        },
        "risks_and_catalysts": {
            **copy.deepcopy(section),
            "risks": [],
            "catalysts": [],
        },
        "outlook": {
            "ipo_day": copy.deepcopy(period),
            "first_week": copy.deepcopy(period),
            "first_two_weeks": copy.deepcopy(period),
            "first_month": copy.deepcopy(period),
        },
    }


def _analysis_response(
    symbol: str,
    listing_date: date,
) -> ai_helper.LLMResponse:
    return ai_helper.LLMResponse(completion=json.dumps(_analysis_payload(symbol, listing_date)))


def _ai_error_response() -> ai_helper.LLMResponse:
    return ai_helper.LLMResponse(
        is_error=True,
        completion="provider rejected the request",
        error_msg="provider rejected the request",
    )


def _run(
    *,
    ai: ai_service_fixtures.OpaqueAIQueue,
    cache=None,
    tokenomics_mode: str = "Standard",
):
    cache = cache or ai_service_fixtures.ExpiringCache()
    with (
        patch.object(
            service.services_crawler_core,
            "fetch_webpage_content",
            new_callable=AsyncMock,
            return_value=_calendar_html(),
        ),
        patch.object(service.cache, "get", side_effect=cache.get),
        patch.object(service.cache, "set", side_effect=cache.set),
        patch.object(service.config.settings_llm_task, "tokenomics_mode", tokenomics_mode),
        patch.object(service.ai_helper, "ai_exec_task", new=ai),
    ):
        return asyncio.run(service.ai_get_asx_new_listings())


def test_filters_orders_and_applies_documented_monetary_eligibility():
    today = _today()
    candidates = [
        _candidate("FUTURE", today + timedelta(days=2)),
        _candidate("PAST", today - timedelta(days=1)),
        _candidate(
            "TODAY",
            today,
            issue_price=None,
            issue_price_upper=None,
            capital_to_raise=None,
        ),
        _candidate("NODATE", None),
        _candidate("ZEROLOW", today + timedelta(days=1), issue_price=0),
        _candidate("ZEROUP", today + timedelta(days=1), issue_price_upper=0),
        _candidate("ZERORAISE", today + timedelta(days=1), capital_to_raise=0),
        _candidate("NANLOW", today + timedelta(days=1), issue_price=float("nan")),
        _candidate("NEGINFUP", today + timedelta(days=1), issue_price_upper=float("-inf")),
        _candidate("NANRAISE", today + timedelta(days=1), capital_to_raise=float("nan")),
    ]

    events = _run(
        ai=ai_service_fixtures.OpaqueAIQueue([_extraction_response(candidates)]),
        tokenomics_mode="Economy",
    )

    assert [event.symbol for event in events] == ["ASX:TODAY", "ASX:FUTURE"]
    assert events[0].issue_price is None
    assert events[0].issue_price_upper is None
    assert events[0].capital_to_raise is None
    assert all(event.analysis_status == "Skipped" for event in events)
    assert events[0].timestamp_str.startswith(today.isoformat())
    assert events[1].timestamp_str.startswith((today + timedelta(days=2)).isoformat())


def test_economy_eligibility_uses_underwriting_and_public_offer_close_date():
    listing_date = _today() + timedelta(days=10)
    today = _today()
    candidates = [
        _candidate("MISSING", listing_date, is_underwritten=False),
        _candidate(
            "PASTCLOSE",
            listing_date,
            is_underwritten=False,
            public_offer_close_date=(today - timedelta(days=1)).isoformat(),
        ),
        _candidate(
            "TODAYCLOSE",
            listing_date,
            is_underwritten=False,
            public_offer_close_date=today.isoformat(),
        ),
        _candidate("UNKNOWN", listing_date, is_underwritten=None),
    ]
    ai = ai_service_fixtures.OpaqueAIQueue(
        [
            _extraction_response(candidates),
            _research_response("ASX:TODAYCLOSE"),
            _analysis_response("ASX:TODAYCLOSE", listing_date),
            _research_response("ASX:UNKNOWN"),
            _analysis_response("ASX:UNKNOWN", listing_date),
        ]
    )

    events = _run(ai=ai, tokenomics_mode="Economy")
    statuses = {event.symbol: event.analysis_status for event in events}

    assert statuses == {
        "ASX:MISSING": "Skipped",
        "ASX:PASTCLOSE": "Skipped",
        "ASX:TODAYCLOSE": "Completed",
        "ASX:UNKNOWN": "Completed",
    }


def test_economy_skip_does_not_consume_cap_but_failed_attempt_does():
    listing_date = _today() + timedelta(days=10)
    candidates = [
        _candidate("A0", listing_date, is_underwritten=False),
        *[
            _candidate(
                f"B{index}",
                listing_date,
                is_underwritten=True,
                public_offer_close_date=(listing_date - timedelta(days=2)).isoformat(),
            )
            for index in range(1, 7)
        ],
    ]
    ai = ai_service_fixtures.OpaqueAIQueue(
        [
            _extraction_response(candidates),
            _research_response("ASX:B1"),
            _analysis_response("ASX:B1", listing_date),
            _ai_error_response(),
            _research_response("ASX:B3"),
            _analysis_response("ASX:B3", listing_date),
            _research_response("ASX:B4"),
            _analysis_response("ASX:B4", listing_date),
            _research_response("ASX:B5"),
            _analysis_response("ASX:B5", listing_date),
        ]
    )

    events = _run(ai=ai, tokenomics_mode="Economy")
    statuses = {event.symbol: event.analysis_status for event in events}

    assert statuses == {
        "ASX:A0": "Skipped",
        "ASX:B1": "Completed",
        "ASX:B2": "Failed",
        "ASX:B3": "Completed",
        "ASX:B4": "Completed",
        "ASX:B5": "Completed",
        "ASX:B6": "Skipped",
    }
    assert next(event for event in events if event.symbol == "ASX:B1").analysis is not None
    failed = next(event for event in events if event.symbol == "ASX:B2")
    assert failed.analysis is None
    assert failed.analysis_error
    assert next(event for event in events if event.symbol == "ASX:B6").analysis is None


def test_unmatched_provider_citations_are_retained_as_unverified_warnings():
    listing_date = _today() + timedelta(days=3)
    candidates = [_candidate("UNVERIFIED", listing_date, is_underwritten=True)]
    ai = ai_service_fixtures.OpaqueAIQueue(
        [
            _extraction_response(candidates),
            _research_response("ASX:UNVERIFIED", verified=False),
            _analysis_response("ASX:UNVERIFIED", listing_date),
        ]
    )

    event = _run(ai=ai)[0]

    assert event.analysis_status == "Completed"
    assert event.analysis is not None
    assert event.analysis.references
    assert all(reference.is_verified is False for reference in event.analysis.references)
    assert event.analysis.executive_summary.data_gaps


def test_repeated_public_call_reuses_completed_analysis_when_ai_is_unavailable():
    listing_date = _today() + timedelta(days=3)
    candidates = [_candidate("CACHE", listing_date, is_underwritten=True)]
    cache = ai_service_fixtures.ExpiringCache()
    ai = ai_service_fixtures.OpaqueAIQueue(
        [
            _extraction_response(candidates),
            _research_response("ASX:CACHE"),
            _analysis_response("ASX:CACHE", listing_date),
        ]
    )

    first = _run(ai=ai, cache=cache)
    second = _run(ai=ai, cache=cache)

    assert second == first
    assert second[0].analysis_status == "Completed"
    assert second[0].analysis is not None


def test_hourly_source_refresh_discovers_new_listings_without_expiring_unchanged_ai_results():
    listing_date = _today() + timedelta(days=3)
    before_html = _calendar_html()
    after_html = before_html.replace("Example issuer.", "Example issuer. Additional issuer BBB.")
    scraper = Mock()
    scraper.get.side_effect = [
        Mock(status_code=200, text=before_html),
        Mock(status_code=200, text=after_html),
        Mock(status_code=200, text=after_html),
    ]
    clock = ai_service_fixtures.ManualClock()
    cache = ai_service_fixtures.ExpiringCache(clock)
    first_candidate = _candidate("AAA", listing_date)
    ai = ai_service_fixtures.OpaqueAIQueue(
        [
            _extraction_response([first_candidate]),
            _research_response("ASX:AAA"),
            _analysis_response("ASX:AAA", listing_date),
            _extraction_response([first_candidate, _candidate("BBB", listing_date)]),
            _research_response("ASX:BBB"),
            _analysis_response("ASX:BBB", listing_date),
        ]
    )
    with (
        patch.object(service.services_crawler_core.cloudscraper, "create_scraper", return_value=scraper),
        patch.object(service.cache, "get", side_effect=cache.get),
        patch.object(service.cache, "set", side_effect=cache.set),
        patch.object(service.config.settings_llm_task, "tokenomics_mode", "Standard"),
        patch.object(service.ai_helper, "ai_exec_task", new=ai),
    ):
        first = asyncio.run(service.ai_get_asx_new_listings())
        clock.advance(1800)
        cached = asyncio.run(service.ai_get_asx_new_listings())
        clock.advance(1800)
        updated = asyncio.run(service.ai_get_asx_new_listings())
        clock.advance(3600)
        reused = asyncio.run(service.ai_get_asx_new_listings())

    assert [event.symbol for event in first] == ["ASX:AAA"]
    assert cached == first
    assert [event.symbol for event in updated] == ["ASX:AAA", "ASX:BBB"]
    assert all(event.analysis_status == "Completed" for event in updated)
    assert reused == updated
    assert not ai.responses


def test_documented_six_hour_cache_expiry_reenters_analysis():
    listing_date = _today() + timedelta(days=3)
    candidates = [_candidate("EXPIRY", listing_date, is_underwritten=True)]
    clock = ai_service_fixtures.ManualClock()
    cache = ai_service_fixtures.ExpiringCache(clock)
    ai = ai_service_fixtures.OpaqueAIQueue(
        [
            _extraction_response(candidates),
            _research_response("ASX:EXPIRY"),
            _analysis_response("ASX:EXPIRY", listing_date),
        ]
    )

    first = _run(ai=ai, cache=cache)
    clock.advance(6 * 60 * 60 - 1)
    assert _run(ai=ai, cache=cache) == first
    clock.advance(1)
    expired = _run(ai=ai, cache=cache)

    assert expired[0].analysis_status == "Failed"
    assert expired[0].analysis is None


def test_opaque_invalid_cache_raises_documented_runtime_error():
    with pytest.raises(RuntimeError):
        _run(
            ai=ai_service_fixtures.OpaqueAIQueue(),
            cache=ai_service_fixtures.InvalidCache(object()),
        )


def test_fetch_failure_raises_documented_runtime_error():
    with (
        patch.object(
            service.services_crawler_core,
            "fetch_webpage_content",
            new_callable=AsyncMock,
            return_value=None,
        ),
        pytest.raises(RuntimeError),
    ):
        asyncio.run(service.ai_get_asx_new_listings())


def test_extraction_error_response_raises_documented_runtime_error():
    with pytest.raises(RuntimeError):
        _run(ai=ai_service_fixtures.OpaqueAIQueue([_ai_error_response()]))


def test_invalid_extraction_payload_raises_value_error():
    with pytest.raises(ValueError):
        _run(ai=ai_service_fixtures.OpaqueAIQueue([ai_helper.LLMResponse(completion='{"listings": "invalid"}')]))


def test_extraction_rate_limit_is_propagated():
    failure = ai_helper.LLMRateLimitError("retry budget exhausted")

    with pytest.raises(ai_helper.LLMRateLimitError) as error_info:
        _run(ai=ai_service_fixtures.OpaqueAIQueue([failure]))

    assert error_info.value is failure
