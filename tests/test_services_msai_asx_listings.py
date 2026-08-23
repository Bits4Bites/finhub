import asyncio
import json
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from app.models import events_listings as models_events_listings
from app.services import ai_helper, msai_asx_listings
from app.utils import ai_reference as ai_reference_utils


@pytest.fixture(autouse=True)
def mock_listings_cache():
    with (
        patch.object(msai_asx_listings.cache, "get", new_callable=AsyncMock, return_value=None) as mock_get,
        patch.object(msai_asx_listings.cache, "set", new_callable=AsyncMock, return_value=True) as mock_set,
    ):
        yield mock_get, mock_set


def _candidate_data(**overrides) -> dict[str, object]:
    data: dict[str, object] = {
        "symbol": "ASX:ABC",
        "company_name": "Alpha Ltd",
        "listing_date": "2099-09-01",
        "issue_price": 1.5,
        "issue_type": "Ordinary fully paid shares",
        "capital_to_raise": 10_000_000,
        "is_underwritten": False,
        "underwriters": [],
        "lead_managers": ["Example Capital"],
        "principal_activities": "Technology services",
        "sector": "TECHNOLOGY",
        "public_offer_close_date": "2099-08-25",
    }
    data.update(overrides)
    return data


def _event(
    symbol: str = "ASX:ABC",
    *,
    is_underwritten: bool | None = False,
) -> models_events_listings.ListingEvent:
    return models_events_listings.ListingEvent(
        symbol=symbol,
        exchange="ASX",
        company_name="Alpha Ltd",
        date="2099-09-01",
        issue_price=1.5,
        issue_type="Ordinary fully paid shares",
        currency="AUD",
        capital_to_raise=10_000_000,
        is_underwritten=is_underwritten,
    )


def _reference_data(
    source_id: str = "asx-source",
    url: str = "https://www.asx.com.au/announcement",
) -> dict[str, object]:
    return {
        "id": source_id,
        "title": "ASX announcement",
        "publisher": "ASX",
        "source_type": "Exchange",
        "published_at": None,
        "accessed_at": "2020-01-01",
        "url": url,
    }


def _research_section_data(source_id: str = "asx-source") -> dict[str, object]:
    return {
        "facts": [{"text": "Verified fact", "reference_ids": [source_id]}],
        "data_gaps": [],
        "reference_ids": [source_id],
    }


def _research_data(
    symbol: str = "ASX:ABC",
    *,
    source_id: str = "asx-source",
    source_url: str = "https://www.asx.com.au/announcement",
) -> dict[str, object]:
    section = _research_section_data(source_id)
    return {
        "symbol": symbol,
        "as_of": "2026-08-19T00:00:00Z",
        "offer": section,
        "business": section,
        "financials": section,
        "valuation": section,
        "governance": section,
        "market_context": section,
        "risks_and_catalysts": section,
        "references": [_reference_data(source_id, source_url)],
    }


def _analysis_section_data() -> dict[str, object]:
    return {
        "summary": "Evidence-based assessment.",
        "data_quality": "High",
        "facts": [{"text": "Verified fact", "reference_ids": ["asx-source"]}],
        "assumptions": [],
        "data_gaps": [],
        "reference_ids": ["asx-source"],
    }


def _period_outlook_data() -> dict[str, object]:
    return {
        "assessment_type": "Forecast",
        "period_end": "2099-09-01",
        "direction": "Up",
        "expected_price_min": 1.6,
        "expected_price_max": 1.8,
        "expected_return_min_pct": 6.6,
        "expected_return_max_pct": 20,
        "confidence": 70,
        "rationale": "Supported by verified demand.",
        "key_drivers": ["Demand"],
        "risk_factors": ["Volatility"],
        "assumptions": ["Stable market"],
        "data_gaps": [],
        "reference_ids": ["asx-source"],
    }


def _analysis_draft_data(symbol: str = "ASX:ABC") -> dict[str, object]:
    section = _analysis_section_data()
    return {
        "symbol": symbol,
        "as_of": "2026-08-19T00:00:00Z",
        "listing_status": "Upcoming",
        "overall_data_quality": "High",
        "executive_summary": section,
        "overall_stance": "Bullish",
        "overall_confidence": 70,
        "offer": {
            **section,
            "issue_price_assessment": "Reasonable.",
            "capital_raise_assessment": "Adequate.",
            "underwriting_assessment": "Not underwritten.",
            "use_of_funds": ["Growth"],
            "dilution_and_escrow": None,
        },
        "business": {
            **section,
            "business_model": "Subscription software.",
            "revenue_sources": ["Subscriptions"],
            "competitive_position": "Emerging participant.",
            "sector_context": "Growing market.",
        },
        "financials": {
            **section,
            "historical_performance": "Revenue growth.",
            "profitability_and_cash_flow": "Pre-profit.",
            "balance_sheet_and_funding": "Offer funds growth.",
            "forecast_quality": "Forecast assumptions disclosed.",
        },
        "valuation": {
            **section,
            "valuation_view": "Within peer range.",
            "implied_market_cap": 50_000_000,
            "peer_comparison": "Comparable to peers.",
            "sensitivity": "Sensitive to growth.",
        },
        "governance": {
            **section,
            "board_and_management": "Relevant experience.",
            "ownership_and_escrow": "Escrow disclosed.",
            "governance_concerns": [],
        },
        "risks_and_catalysts": {
            **section,
            "risks": [
                {
                    "title": "Execution",
                    "description": "Growth may be slower than planned.",
                    "severity": "High",
                    "likelihood": "Medium",
                    "horizon": "First Month",
                    "reference_ids": ["asx-source"],
                }
            ],
            "catalysts": [
                {
                    "title": "Demand",
                    "description": "Strong customer demand.",
                    "likelihood": "Medium",
                    "horizon": "First Month",
                    "reference_ids": ["asx-source"],
                }
            ],
        },
        "outlook": {
            "ipo_day": _period_outlook_data(),
            "first_week": _period_outlook_data(),
            "first_two_weeks": _period_outlook_data(),
            "first_month": _period_outlook_data(),
        },
    }


def _research_model(*, is_verified: bool = True) -> msai_asx_listings._ListingResearch:
    data = _research_data()
    data["references"] = [
        {
            **_reference_data(),
            "is_verified": is_verified,
        }
    ]
    return msai_asx_listings._ListingResearch.model_validate(data)


def _analysis_model() -> models_events_listings.ListingAnalysis:
    data = _analysis_draft_data()
    data["references"] = [
        {
            **_reference_data(),
            "is_verified": True,
        }
    ]
    return models_events_listings.ListingAnalysis.model_validate(data)


def test_private_extraction_schema_parses_candidates_and_rejects_unknown_fields():
    response = msai_asx_listings._ExtractedListingsResponse.model_validate({"listings": [_candidate_data()]})

    assert response.listings[0].listing_date == date(2099, 9, 1)
    assert response.listings[0].issue_price == 1.5

    with pytest.raises(ValidationError):
        msai_asx_listings._ExtractedListingsResponse.model_validate({"listings": [], "unexpected": True})


def test_private_research_schema_rejects_unknown_reference_ids():
    data = _research_data()
    data["offer"] = {
        **_research_section_data(),
        "reference_ids": ["missing-source"],
    }

    with pytest.raises(ValidationError, match="unknown reference IDs"):
        msai_asx_listings._ListingResearchDraft.model_validate(data)


def test_private_research_schema_rejects_blank_or_duplicate_temporary_ids():
    blank_id_data = _research_data(source_id=" ")
    duplicate_id_data = _research_data()
    duplicate_id_data["references"].append(_reference_data(url="https://example.com/second-source"))

    with pytest.raises(ValidationError):
        msai_asx_listings._ListingResearchDraft.model_validate(blank_id_data)
    with pytest.raises(ValidationError, match="reference IDs must be unique"):
        msai_asx_listings._ListingResearchDraft.model_validate(duplicate_id_data)


def test_quick_research_schema_enforces_source_and_fact_limits():
    schema = msai_asx_listings._ListingResearchDraft.model_json_schema()
    data = _research_data()
    data["offer"] = {
        **_research_section_data(),
        "facts": _research_section_data()["facts"] * 4,
    }

    assert schema["properties"]["references"]["maxItems"] == 5
    with pytest.raises(ValidationError):
        msai_asx_listings._ListingResearchDraft.model_validate(data)


def test_quick_analysis_schema_limits_risks_and_catalysts():
    data = _analysis_draft_data()
    risk = data["risks_and_catalysts"]["risks"][0]
    catalyst = data["risks_and_catalysts"]["catalysts"][0]
    data["risks_and_catalysts"]["risks"] = [risk] * 4
    data["risks_and_catalysts"]["catalysts"] = [catalyst] * 4

    with pytest.raises(ValidationError):
        msai_asx_listings._ListingAnalysisDraft.model_validate(data)


def test_extracts_structured_listings_and_retains_unavailable_offer_values(mock_listings_cache):
    response_data = {
        "listings": [
            _candidate_data(symbol="ASX:LATE", listing_date="2099-09-03"),
            _candidate_data(symbol="ASX:EARLY", listing_date="2099-09-01"),
            _candidate_data(symbol="ASX:NO_DATE", listing_date=None),
            _candidate_data(
                symbol="ASX:EF2",
                company_name="Energy Fuels Inc.",
                issue_price=None,
                issue_type="CDI 1:1 Foreign Exempt",
                capital_to_raise=None,
                public_offer_close_date=None,
                is_underwritten=None,
            ),
            _candidate_data(symbol="ASX:ZERO_PRICE", issue_price=0),
            _candidate_data(symbol="ASX:ZERO_CAPITAL", capital_to_raise=0),
            _candidate_data(symbol="INVALID-SYMBOL"),
        ]
    }
    llm_response = ai_helper.LLMResponse(completion=json.dumps(response_data))
    html = '<div class="multi-column-height">Listing date: details</div>'

    with (
        patch.object(
            msai_asx_listings.services_crawler,
            "fetch_webpage_content",
            new_callable=AsyncMock,
            return_value=html,
        ),
        patch.object(
            msai_asx_listings.ai_helper,
            "ai_exec_task",
            new_callable=AsyncMock,
            return_value=llm_response,
        ) as mock_ai_exec,
    ):
        events = asyncio.run(msai_asx_listings._get_asx_new_listings())

    assert [event.symbol for event in events] == ["ASX:LATE", "ASX:EARLY", "ASX:EF2"]
    assert events[-1].issue_price is None
    assert events[-1].capital_to_raise is None
    assert mock_ai_exec.await_args.args[0] == "ASX_LISTTINGS_EXTRACT"
    assert mock_ai_exec.await_args.kwargs["schema_name"] == "asx_listing_extraction"
    assert mock_ai_exec.await_args.kwargs["response_json_schema"] == (
        msai_asx_listings._ExtractedListingsResponse.model_json_schema()
    )
    _, mock_cache_set = mock_listings_cache
    mock_cache_set.assert_awaited_once()
    assert mock_cache_set.await_args.kwargs["ttl"] == 24 * 60 * 60


def test_extraction_reuses_cached_structured_result(mock_listings_cache):
    mock_cache_get, mock_cache_set = mock_listings_cache
    mock_cache_get.return_value = {"listings": [_candidate_data()]}
    html = '<div class="multi-column-height">Listing date: details</div>'

    with (
        patch.object(
            msai_asx_listings.services_crawler,
            "fetch_webpage_content",
            new_callable=AsyncMock,
            return_value=html,
        ),
        patch.object(msai_asx_listings.ai_helper, "ai_exec_task", new_callable=AsyncMock) as mock_ai_exec,
    ):
        events = asyncio.run(msai_asx_listings._get_asx_new_listings())

    assert [event.symbol for event in events] == ["ASX:ABC"]
    mock_ai_exec.assert_not_awaited()
    mock_cache_set.assert_not_awaited()


def test_research_marks_provider_verified_sources(mock_listings_cache):
    llm_response = ai_helper.LLMResponse(
        completion=json.dumps(_research_data()),
        citation_urls=["https://www.asx.com.au/announcement"],
    )

    with patch.object(
        msai_asx_listings.ai_helper,
        "ai_exec_task",
        new_callable=AsyncMock,
        return_value=llm_response,
    ) as mock_ai_exec:
        research = asyncio.run(msai_asx_listings._research_asx_listing(_event(is_underwritten=None)))

    expected_source_id = ai_reference_utils.generate_source_id("https://www.asx.com.au/announcement")
    assert research.references[0].id == expected_source_id
    assert ai_reference_utils.collect_reference_ids(research) == {expected_source_id}
    assert research.references[0].is_verified is True
    assert research.references[0].accessed_at.year > 2020
    assert mock_ai_exec.await_args.args[0] == "ASX_LISTTINGS_RESEARCH"
    assert "quick, bounded research pass" in mock_ai_exec.await_args.args[1]
    assert "no more than five high-value sources" in mock_ai_exec.await_args.args[1]
    assert "Do not perform exhaustive due diligence" in mock_ai_exec.await_args.args[1]
    assert "exact cited HTTPS URL" in mock_ai_exec.await_args.args[1]
    assert "explicitly underwritten" not in mock_ai_exec.await_args.args[1]
    assert mock_ai_exec.await_args.kwargs["schema_name"] == "asx_listing_research"
    assert mock_ai_exec.await_args.kwargs["response_json_schema"] == (
        msai_asx_listings._ListingResearchDraft.model_json_schema()
    )
    _, mock_cache_set = mock_listings_cache
    mock_cache_set.assert_awaited_once()
    assert mock_cache_set.await_args.kwargs["ttl"] == 24 * 60 * 60


def test_research_reuses_cached_validated_result(mock_listings_cache):
    mock_cache_get, mock_cache_set = mock_listings_cache
    expected = _research_model()
    mock_cache_get.return_value = expected.model_dump(mode="json")

    with patch.object(msai_asx_listings.ai_helper, "ai_exec_task", new_callable=AsyncMock) as mock_ai_exec:
        research = asyncio.run(msai_asx_listings._research_asx_listing(_event()))

    assert research == expected
    assert research is not expected
    mock_ai_exec.assert_not_awaited()
    mock_cache_set.assert_not_awaited()


def test_underwritten_listing_selects_underwritten_research_task():
    llm_response = ai_helper.LLMResponse(
        completion=json.dumps(_research_data()),
        citation_urls=["https://www.asx.com.au/announcement"],
    )

    with patch.object(
        msai_asx_listings.ai_helper,
        "ai_exec_task",
        new_callable=AsyncMock,
        return_value=llm_response,
    ) as mock_ai_exec:
        asyncio.run(msai_asx_listings._research_asx_listing(_event(is_underwritten=True)))

    assert mock_ai_exec.await_args.args[0] == "ASX_LISTTINGS_UNDERWRITTEN_RESEARCH"
    assert "explicitly underwritten" in mock_ai_exec.await_args.args[1]
    assert "termination rights" in mock_ai_exec.await_args.args[1]


def test_research_accepts_empty_provider_citations_and_marks_source_unverified():
    llm_response = ai_helper.LLMResponse(
        completion=json.dumps(_research_data()),
        citation_urls=[],
    )

    with patch.object(
        msai_asx_listings.ai_helper,
        "ai_exec_task",
        new_callable=AsyncMock,
        return_value=llm_response,
    ):
        research = asyncio.run(msai_asx_listings._research_asx_listing(_event()))

    assert research.references[0].is_verified is False


def test_research_repairs_orphan_links_and_discards_unsupported_facts():
    response_data = _research_data()
    response_data["offer"] = {
        **_research_section_data(),
        "facts": [
            *_research_section_data()["facts"],
            {
                "text": "Unsupported orphan fact",
                "reference_ids": ["source-6"],
            },
        ],
        "reference_ids": ["asx-source", "source-6"],
    }
    response_data["references"].append(
        _reference_data(
            "unused-source",
            "https://example.com/unused",
        )
    )
    llm_response = ai_helper.LLMResponse(
        completion=json.dumps(response_data),
        citation_urls=["https://www.asx.com.au/announcement"],
    )

    with patch.object(
        msai_asx_listings.ai_helper,
        "ai_exec_task",
        new_callable=AsyncMock,
        return_value=llm_response,
    ):
        research = asyncio.run(msai_asx_listings._research_asx_listing(_event()))

    assert len(research.references) == 1
    assert {fact.text for fact in research.offer.facts} == {"Verified fact"}
    assert any(
        "source-6" in data_gap and "Removed 1 unsupported fact" in data_gap for data_gap in research.offer.data_gaps
    )
    assert "source-6" not in ai_reference_utils.collect_reference_ids(research)


def test_research_replaces_url_temporary_id_and_remaps_all_references():
    source_url = "https://scx.ai/investors"
    llm_response = ai_helper.LLMResponse(
        completion=json.dumps(
            _research_data(
                symbol="ASX:SCX",
                source_id=source_url,
                source_url=source_url,
            )
        ),
        citation_urls=[f"{source_url}/"],
    )

    with patch.object(
        msai_asx_listings.ai_helper,
        "ai_exec_task",
        new_callable=AsyncMock,
        return_value=llm_response,
    ):
        research = asyncio.run(msai_asx_listings._research_asx_listing(_event("ASX:SCX")))

    expected_source_id = ai_reference_utils.generate_source_id(source_url)
    assert research.references[0].id == expected_source_id
    assert research.references[0].is_verified is True
    assert ai_reference_utils.collect_reference_ids(research) == {expected_source_id}
    assert expected_source_id == ai_reference_utils.generate_source_id(f"{source_url}/")


def test_research_marks_mismatched_source_urls_unverified():
    llm_response = ai_helper.LLMResponse(
        completion=json.dumps(_research_data()),
        citation_urls=["https://example.com/different-source"],
    )

    with patch.object(
        msai_asx_listings.ai_helper,
        "ai_exec_task",
        new_callable=AsyncMock,
        return_value=llm_response,
    ):
        research = asyncio.run(msai_asx_listings._research_asx_listing(_event()))

    assert research.references[0].is_verified is False


@pytest.mark.parametrize("is_verified", [True, False])
def test_assessment_uses_structured_response_and_preserves_source_verification(
    is_verified,
    mock_listings_cache,
):
    llm_response = ai_helper.LLMResponse(completion=json.dumps(_analysis_draft_data()))

    with patch.object(
        msai_asx_listings.ai_helper,
        "ai_exec_task",
        new_callable=AsyncMock,
        return_value=llm_response,
    ) as mock_ai_exec:
        analysis = asyncio.run(
            msai_asx_listings._assess_asx_listing(
                _event(),
                _research_model(is_verified=is_verified),
            )
        )

    assert analysis.symbol == "ASX:ABC"
    assert str(analysis.references[0].url) == "https://www.asx.com.au/announcement"
    assert analysis.references[0].is_verified is is_verified
    assert set(type(analysis.outlook).model_fields) == {
        "ipo_day",
        "first_week",
        "first_two_weeks",
        "first_month",
    }
    assert mock_ai_exec.await_args.args[0] == "ASX_LISTTINGS_ANALYZE"
    assert "quick, first-pass assessment" in mock_ai_exec.await_args.args[1]
    assert "not deep investment research" in mock_ai_exec.await_args.args[1]
    assert "at most three risks and three catalysts" in mock_ai_exec.await_args.args[1]
    assert "explicitly underwritten" not in mock_ai_exec.await_args.args[1]
    assert mock_ai_exec.await_args.kwargs["schema_name"] == "asx_listing_analysis"
    assert mock_ai_exec.await_args.kwargs["response_json_schema"] == (
        msai_asx_listings._ListingAnalysisDraft.model_json_schema()
    )
    _, mock_cache_set = mock_listings_cache
    mock_cache_set.assert_awaited_once()
    assert mock_cache_set.await_args.kwargs["ttl"] == 24 * 60 * 60


def test_assessment_reuses_cached_validated_result(mock_listings_cache):
    mock_cache_get, mock_cache_set = mock_listings_cache
    expected = _analysis_model()
    mock_cache_get.return_value = expected.model_dump(mode="json")

    with patch.object(msai_asx_listings.ai_helper, "ai_exec_task", new_callable=AsyncMock) as mock_ai_exec:
        analysis = asyncio.run(
            msai_asx_listings._assess_asx_listing(
                _event(),
                _research_model(),
            )
        )

    assert analysis == expected
    assert analysis is not expected
    mock_ai_exec.assert_not_awaited()
    mock_cache_set.assert_not_awaited()


@pytest.mark.parametrize(
    ("listing_date", "expected_ttl"),
    [
        ("2026-06-15", 60 * 60),
        ("2026-06-16", 60 * 60),
        ("2026-06-22", 6 * 60 * 60),
        ("2026-06-23", 24 * 60 * 60),
    ],
)
def test_listing_cache_ttl_shortens_near_listing_date(listing_date, expected_ttl):
    event = _event()
    event.date = listing_date

    assert msai_asx_listings._listing_cache_ttl(event, today=date(2026, 6, 15)) == expected_ttl


def test_underwritten_listing_selects_underwritten_analysis_task():
    llm_response = ai_helper.LLMResponse(completion=json.dumps(_analysis_draft_data()))

    with patch.object(
        msai_asx_listings.ai_helper,
        "ai_exec_task",
        new_callable=AsyncMock,
        return_value=llm_response,
    ) as mock_ai_exec:
        asyncio.run(
            msai_asx_listings._assess_asx_listing(
                _event(is_underwritten=True),
                _research_model(),
            )
        )

    assert mock_ai_exec.await_args.args[0] == "ASX_LISTTINGS_UNDERWRITTEN_ANALYZE"
    assert "explicitly underwritten" in mock_ai_exec.await_args.args[1]
    assert "proof of investor demand" in mock_ai_exec.await_args.args[1]


def test_per_stock_pipeline_reports_partial_failures_explicitly():
    events = [_event("ASX:ABC"), _event("ASX:XYZ")]
    research = _research_model()
    analysis = _analysis_model()

    with (
        patch.object(
            msai_asx_listings,
            "_research_asx_listing",
            new_callable=AsyncMock,
            side_effect=[research, RuntimeError("research failed")],
        ) as mock_research,
        patch.object(
            msai_asx_listings,
            "_assess_asx_listing",
            new_callable=AsyncMock,
            return_value=analysis,
        ) as mock_assess,
    ):
        result = asyncio.run(msai_asx_listings._analyze_asx_listings(events))

    assert [event.analysis_status for event in result] == ["Completed", "Failed"]
    assert result[1].analysis_error == "AI listing analysis failed"
    assert mock_research.await_count == 2
    assert mock_assess.await_count == 1
