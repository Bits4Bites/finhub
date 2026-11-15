import asyncio
import copy
import json
from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest

from app.models import events_listings as models_listings
from app.services import ai_helper
from app.services import msai_asx_listings as service
from app.utils import ai_reference

_SYDNEY_TZ = ZoneInfo("Australia/Sydney")
_SOURCE_URL = "https://www.asx.com.au/markets/company/ABC"
_SOURCE_ID = ai_reference.generate_source_id(_SOURCE_URL)


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


def _extraction_response(candidates: list[dict[str, object]]) -> ai_helper.LLMResponse:
    return ai_helper.LLMResponse(
        completion=json.dumps({"listings": candidates}),
    )


def _research_response(symbol: str) -> ai_helper.LLMResponse:
    section = {
        "facts": [
            {
                "text": "The issuer disclosed its offer and business activities.",
                "reference_ids": [_SOURCE_URL],
            }
        ],
        "data_gaps": [],
        "reference_ids": [_SOURCE_URL],
    }
    payload = {
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
                "id": _SOURCE_URL,
                "title": "ASX listing information",
                "publisher": "ASX",
                "source_type": "Exchange",
                "published_at": None,
                "accessed_at": datetime.now(UTC).isoformat(),
                "url": _SOURCE_URL,
            }
        ],
    }
    return ai_helper.LLMResponse(
        completion=json.dumps(payload),
        citation_urls=[_SOURCE_URL],
    )


def _analysis_section() -> dict[str, object]:
    return {
        "summary": "Evidence-based assessment.",
        "data_quality": "High",
        "facts": [
            {
                "text": "The issuer disclosed its offer and business activities.",
                "reference_ids": [_SOURCE_ID],
            }
        ],
        "assumptions": [],
        "data_gaps": [],
        "reference_ids": [_SOURCE_ID],
    }


def _analysis_response(symbol: str, listing_date: date) -> ai_helper.LLMResponse:
    section = _analysis_section()
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
        "reference_ids": [_SOURCE_ID],
    }
    payload = {
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
    return ai_helper.LLMResponse(completion=json.dumps(payload))


def _run_with_boundaries(
    *,
    ai_side_effect,
    cache_get=None,
    tokenomics_mode: str = "Standard",
):
    cache_get = cache_get or AsyncMock(return_value=None)
    with (
        patch.object(
            service.services_crawler_core,
            "fetch_webpage_content",
            new_callable=AsyncMock,
            return_value=_calendar_html(),
        ),
        patch.object(service.cache, "get", cache_get),
        patch.object(
            service.cache,
            "set",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch.object(
            service.config.settings_llm_task,
            "tokenomics_mode",
            tokenomics_mode,
        ),
        patch.object(
            service.ai_helper,
            "ai_exec_task",
            new_callable=AsyncMock,
            side_effect=ai_side_effect,
        ) as ai_exec,
    ):
        return asyncio.run(service.ai_get_asx_new_listings()), ai_exec


def test_returns_only_confirmed_current_and_future_listings_in_order():
    today = _today()
    candidates = [
        _candidate("FUTURE", today + timedelta(days=2)),
        _candidate("PAST", today - timedelta(days=1)),
        _candidate(
            "TODAY",
            today,
            issue_price=None,
            capital_to_raise=None,
        ),
        _candidate("NODATE", None),
        _candidate("ZERO", today + timedelta(days=1), issue_price=0),
    ]

    events, ai_exec = _run_with_boundaries(
        ai_side_effect=[_extraction_response(candidates)],
        tokenomics_mode="Economy",
    )

    assert [event.symbol for event in events] == ["ASX:TODAY", "ASX:FUTURE"]
    assert events[0].issue_price is None
    assert events[0].capital_to_raise is None
    assert all(event.analysis_status == "Skipped" for event in events)
    assert events[0].timestamp_str.startswith(today.isoformat())
    assert events[1].timestamp_str.startswith((today + timedelta(days=2)).isoformat())
    assert all(event.timestamp > 0 for event in events)
    assert [call.args[0] for call in ai_exec.await_args_list] == ["ASX_LISTTINGS_EXTRACT"]


def test_analysis_attempt_cap_retains_completed_failed_and_skipped_events():
    listing_date = _today() + timedelta(days=10)
    candidates = [
        _candidate(
            f"A{index}",
            listing_date,
            is_underwritten=True,
            public_offer_close_date=(listing_date - timedelta(days=2)).isoformat(),
        )
        for index in range(1, 8)
    ]
    responses: list[ai_helper.LLMResponse] = [_extraction_response(candidates)]
    for index in range(1, 6):
        symbol = f"ASX:A{index}"
        if index == 2:
            responses.append(
                ai_helper.LLMResponse(
                    is_error=True,
                    error_msg="research unavailable",
                )
            )
            continue
        responses.extend(
            [
                _research_response(symbol),
                _analysis_response(symbol, listing_date),
            ]
        )

    events, ai_exec = _run_with_boundaries(ai_side_effect=responses)

    assert [event.symbol for event in events] == [
        "ASX:A1",
        "ASX:A2",
        "ASX:A3",
        "ASX:A4",
        "ASX:A5",
        "ASX:A6",
        "ASX:A7",
    ]
    assert [event.analysis_status for event in events] == [
        "Completed",
        "Failed",
        "Completed",
        "Completed",
        "Completed",
        "Skipped",
        "Skipped",
    ]
    assert events[0].analysis is not None
    assert events[0].analysis.references[0].is_verified is True
    assert events[1].analysis is None
    assert events[1].analysis_error == "AI listing analysis failed"
    assert all(event.analysis is None for event in events[5:])
    assert ai_exec.await_count == 10


def test_fetch_failure_is_reported_to_caller():
    with (
        patch.object(
            service.services_crawler_core,
            "fetch_webpage_content",
            new_callable=AsyncMock,
            return_value=None,
        ),
        pytest.raises(RuntimeError, match="Failed to fetch the ASX"),
    ):
        asyncio.run(service.ai_get_asx_new_listings())


def test_ai_extraction_failure_is_reported_to_caller():
    with (
        patch.object(
            service.services_crawler_core,
            "fetch_webpage_content",
            new_callable=AsyncMock,
            return_value=_calendar_html(),
        ),
        patch.object(service.cache, "get", new_callable=AsyncMock, return_value=None),
        patch.object(
            service.ai_helper,
            "ai_exec_task",
            new_callable=AsyncMock,
            return_value=ai_helper.LLMResponse(
                is_error=True,
                error_msg="extraction failed",
            ),
        ),
        pytest.raises(RuntimeError, match="AI extraction failed"),
    ):
        asyncio.run(service.ai_get_asx_new_listings())


def test_invalid_ai_extraction_payload_is_reported_to_caller():
    with (
        patch.object(
            service.services_crawler_core,
            "fetch_webpage_content",
            new_callable=AsyncMock,
            return_value=_calendar_html(),
        ),
        patch.object(service.cache, "get", new_callable=AsyncMock, return_value=None),
        patch.object(
            service.ai_helper,
            "ai_exec_task",
            new_callable=AsyncMock,
            return_value=ai_helper.LLMResponse(completion='{"listings": "invalid"}'),
        ),
        pytest.raises(ValueError, match="invalid structured response"),
    ):
        asyncio.run(service.ai_get_asx_new_listings())


@pytest.mark.parametrize("cache_stage", ["extraction", "analysis"])
def test_invalid_cache_values_are_reported_to_caller(cache_stage):
    today = _today()
    extracted = {
        "listings": [
            _candidate(
                "ABC",
                today + timedelta(days=3),
                is_underwritten=False,
            )
        ]
    }
    cache_values = [object()] if cache_stage == "extraction" else [extracted, "not a listing-event list"]

    with (
        patch.object(
            service.services_crawler_core,
            "fetch_webpage_content",
            new_callable=AsyncMock,
            return_value=_calendar_html(),
        ),
        patch.object(
            service.cache,
            "get",
            new_callable=AsyncMock,
            side_effect=cache_values,
        ),
        patch.object(
            service.config.settings_llm_task,
            "tokenomics_mode",
            "Economy",
        ),
        pytest.raises(RuntimeError, match="cache contains an invalid value"),
    ):
        asyncio.run(service.ai_get_asx_new_listings())


def test_cached_completed_events_are_returned_as_independent_models():
    today = _today()
    extracted = {
        "listings": [
            _candidate(
                "ABC",
                today + timedelta(days=3),
                is_underwritten=True,
            )
        ]
    }
    cached_event = models_listings.ListingEvent(
        symbol="ASX:ABC",
        exchange="ASX",
        company_name="ABC Limited",
        timestamp_str=f"{(today + timedelta(days=3)).isoformat()} 00:00:00+11:00",
        issue_price=1.5,
        currency="AUD",
        capital_to_raise=10_000_000,
        analysis_status="Completed",
    )
    cache_values = iter([extracted, [cached_event]])

    with (
        patch.object(
            service.services_crawler_core,
            "fetch_webpage_content",
            new_callable=AsyncMock,
            return_value=_calendar_html(),
        ),
        patch.object(
            service.cache,
            "get",
            new_callable=AsyncMock,
            side_effect=lambda _key: next(cache_values),
        ),
        patch.object(
            service.ai_helper,
            "ai_exec_task",
            new_callable=AsyncMock,
        ) as ai_exec,
    ):
        result = asyncio.run(service.ai_get_asx_new_listings())

    assert result == [cached_event]
    assert result[0] is not cached_event
    ai_exec.assert_not_awaited()
