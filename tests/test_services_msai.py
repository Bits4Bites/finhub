"""Tests for the staged ticker-analysis service."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from app.models import ai_ticker as models_ticker
from app.schemas import ai_ticker as schemas_ticker
from app.services import ai_helper
from app.services import msai_analyze_ticker as services_ticker
from tests import ticker_fixtures


def _assert_openai_strict_objects(value):
    if isinstance(value, dict):
        if value.get("type") == "object":
            assert value.get("additionalProperties") is False
            assert set(value.get("required", [])) == set(value.get("properties", {}))
        if "$ref" in value:
            assert set(value) == {"$ref"}
        for nested_value in value.values():
            _assert_openai_strict_objects(nested_value)
    elif isinstance(value, list):
        for nested_value in value:
            _assert_openai_strict_objects(nested_value)


def test_ai_response_schemas_are_openai_compatible_and_strict():
    for response_model in (
        services_ticker._TickerResearchResponse,
        services_ticker._TickerForecastResponse,
        services_ticker._TickerRecommendationDraft,
    ):
        schema = ai_helper._openai_compatible_json_schema(response_model.model_json_schema())
        _assert_openai_strict_objects(schema)


def test_holding_snapshot_uses_verified_market_price():
    holding = schemas_ticker.TickerHoldingInput(num_shares=10, avg_price=80)

    snapshot = services_ticker._build_holding_snapshot(
        holding,
        ticker_fixtures.make_market_snapshot(),
    )

    assert snapshot is not None
    assert snapshot.cost_basis == 800
    assert snapshot.market_value == 1_000
    assert snapshot.unrealized_profit_loss == 200
    assert snapshot.unrealized_return_pct == 25
    assert snapshot.break_even_price == 80


def test_ticker_analysis_requires_four_ordered_horizons():
    analysis = ticker_fixtures.make_analysis()
    payload = analysis.model_dump()
    payload["forecasts"] = list(reversed(payload["forecasts"]))

    with pytest.raises(ValidationError, match="four required horizons in order"):
        models_ticker.TickerAnalysis.model_validate(payload)


def test_recommendation_enforces_action_specific_range():
    with pytest.raises(ValidationError, match="BUY requires only buy_range"):
        models_ticker.TickerRecommendation(
            action="BUY",
            scope="NewPosition",
            confidence=70,
            summary="Invalid recommendation.",
            buy_range=None,
            sell_range=None,
            reasoning=["Reason"],
            key_conditions=[],
            reassessment_triggers=[],
            risk_warnings=[],
            reference_ids=[ticker_fixtures.SOURCE_ID],
        )


def test_analysis_rejects_unknown_reference_ids():
    analysis = ticker_fixtures.make_analysis()
    payload = analysis.model_dump()
    payload["recommendation"]["reference_ids"] = ["src-unknown"]

    with pytest.raises(ValueError, match="unknown reference IDs"):
        models_ticker.TickerAnalysis.model_validate(payload)


def test_research_repair_drops_orphan_claim_and_records_gap():
    source = services_ticker._TickerResearchSourceMetadata(
        id=ticker_fixtures.SOURCE_URL,
        title="Issuer research",
        publisher="Example",
        source_type="Research",
        published_at=ticker_fixtures.AS_OF,
        accessed_at=None,
        url=ticker_fixtures.SOURCE_URL,
    )
    valid_claim = {
        "text": "Supported claim.",
        "reference_ids": [ticker_fixtures.SOURCE_URL],
    }
    invalid_claim = {
        "text": "Unsupported claim.",
        "reference_ids": ["https://missing.example/source"],
    }
    section = {
        "summary": "Section summary.",
        "data_quality": "High",
        "claims": [valid_claim, invalid_claim],
        "data_gaps": [],
        "reference_ids": [ticker_fixtures.SOURCE_URL, "https://missing.example/source"],
    }
    response = services_ticker._TickerResearchResponse(
        symbol="NASDAQ:AAPL",
        business_profile=section,
        financial_performance={**section, "claims": [valid_claim]},
        valuation={**section, "claims": [valid_claim]},
        recent_developments={**section, "claims": [valid_claim]},
        catalysts={**section, "claims": [valid_claim]},
        risks={**section, "claims": [valid_claim]},
        market_consensus={**section, "claims": [valid_claim]},
        asset_specific={**section, "claims": [valid_claim]},
        data_gaps=[],
        references=[source],
    )

    repaired = services_ticker._repair_research_references(response)

    assert len(repaired.business_profile.claims) == 1
    assert repaired.business_profile.summary == "Supported claim."
    assert repaired.business_profile.data_quality == "Low"
    assert "Ignored unsupported source links" in repaired.business_profile.data_gaps[0]
    assert "Removed 1 unsupported claim" in repaired.data_gaps[0]


def test_finalize_forecasts_recomputes_returns_and_direction():
    draft = services_ticker._TickerForecastResponse(
        symbol="NASDAQ:AAPL",
        forecasts=[
            {
                "horizon": horizon,
                "assessment_status": "Forecast",
                "expected_price_min": 105 + index,
                "expected_price_max": 110 + index,
                "confidence": 70,
                "rationale": "Sourced forecast.",
                "key_drivers": ["Growth"],
                "risk_factors": ["Volatility"],
                "assumptions": ["Stable market"],
                "data_gaps": [],
                "reference_ids": [ticker_fixtures.SOURCE_ID],
            }
            for index, horizon in enumerate(services_ticker._HORIZON_ORDER)
        ],
        overall_data_quality="High",
        data_gaps=[],
    )

    result = services_ticker._finalize_forecasts(
        draft,
        ticker_fixtures.make_baseline(),
        ticker_fixtures.make_research(),
    )

    assert [forecast.horizon for forecast in result.forecasts] == list(services_ticker._HORIZON_ORDER)
    assert result.forecasts[0].direction == "Up"
    assert result.forecasts[0].expected_return_min_pct == pytest.approx(5)
    assert result.forecasts[0].expected_return_max_pct == pytest.approx(10)


def test_finalize_forecasts_rejects_range_outside_deterministic_envelope():
    draft = services_ticker._TickerForecastResponse(
        symbol="NASDAQ:AAPL",
        forecasts=[
            {
                "horizon": horizon,
                "assessment_status": "Forecast",
                "expected_price_min": 100,
                "expected_price_max": 130,
                "confidence": 70,
                "rationale": "Sourced forecast.",
                "key_drivers": [],
                "risk_factors": [],
                "assumptions": [],
                "data_gaps": [],
                "reference_ids": [ticker_fixtures.SOURCE_ID],
            }
            for horizon in services_ticker._HORIZON_ORDER
        ],
        overall_data_quality="High",
        data_gaps=[],
    )

    with pytest.raises(ValueError, match="outside its deterministic envelope"):
        services_ticker._finalize_forecasts(
            draft,
            ticker_fixtures.make_baseline(),
            ticker_fixtures.make_research(),
        )


def test_forecast_quality_is_insufficient_when_all_horizons_lack_envelopes():
    baseline = ticker_fixtures.make_baseline()
    baseline = baseline.model_copy(
        update={
            "forecast_envelopes": [
                services_ticker._ForecastEnvelope(
                    horizon=horizon,
                    sample_count=0,
                    data_gaps=["Insufficient history."],
                )
                for horizon in services_ticker._HORIZON_ORDER
            ]
        }
    )
    draft = services_ticker._TickerForecastResponse(
        symbol="NASDAQ:AAPL",
        forecasts=[
            {
                "horizon": horizon,
                "assessment_status": "InsufficientData",
                "expected_price_min": None,
                "expected_price_max": None,
                "confidence": 80,
                "rationale": "History is insufficient.",
                "key_drivers": [],
                "risk_factors": [],
                "assumptions": [],
                "data_gaps": ["Insufficient history."],
                "reference_ids": [],
            }
            for horizon in services_ticker._HORIZON_ORDER
        ],
        overall_data_quality="High",
        data_gaps=["Insufficient history."],
    )

    result = services_ticker._finalize_forecasts(
        draft,
        baseline,
        ticker_fixtures.make_research(),
    )

    assert result.overall_data_quality == "Insufficient"
    assert {forecast.confidence for forecast in result.forecasts} == {25}
    assert (
        services_ticker._overall_data_quality(
            ticker_fixtures.make_research(),
            result,
        )
        == "Insufficient"
    )


def test_final_cache_key_isolated_by_holding_but_research_is_shared():
    baseline = ticker_fixtures.make_baseline()
    snapshot = baseline.snapshot
    holding_a = services_ticker._build_holding_snapshot(
        schemas_ticker.TickerHoldingInput(num_shares=10, avg_price=80),
        snapshot,
    )
    holding_b = services_ticker._build_holding_snapshot(
        schemas_ticker.TickerHoldingInput(num_shares=20, avg_price=90),
        snapshot,
    )

    with patch(
        "app.services.msai_analyze_ticker.cache.generate_hourly_key",
        side_effect=lambda *parts: repr(parts),
    ):
        no_holding_key = services_ticker._final_cache_key(
            baseline=baseline,
            intent=None,
            holding_snapshot=None,
        )
        holding_a_key = services_ticker._final_cache_key(
            baseline=baseline,
            intent=None,
            holding_snapshot=holding_a,
        )
        holding_b_key = services_ticker._final_cache_key(
            baseline=baseline,
            intent=None,
            holding_snapshot=holding_b,
        )

    assert len({no_holding_key, holding_a_key, holding_b_key}) == 3
    assert "holding_snapshot" not in services_ticker._research_ticker.__annotations__
    assert "holding_snapshot" not in services_ticker._forecast_ticker.__annotations__


def test_stage_cache_reuses_research_and_forecast_but_isolates_holding():
    baseline = ticker_fixtures.make_baseline()
    research = ticker_fixtures.make_research()
    forecasts = ticker_fixtures.make_forecasts()
    recommendation = ticker_fixtures.make_recommendation()
    holding_a = services_ticker._build_holding_snapshot(
        schemas_ticker.TickerHoldingInput(num_shares=10, avg_price=80),
        baseline.snapshot,
    )
    holding_b = services_ticker._build_holding_snapshot(
        schemas_ticker.TickerHoldingInput(num_shares=20, avg_price=90),
        baseline.snapshot,
    )

    async def collect_keys():
        with patch(
            "app.services.msai_analyze_ticker.cache.get",
            new_callable=AsyncMock,
            return_value=research,
        ) as cache_get:
            await services_ticker._research_ticker(baseline, intent="Growth")
            await services_ticker._research_ticker(baseline, intent="Growth")
        research_keys = [call.args[0] for call in cache_get.await_args_list]

        with patch(
            "app.services.msai_analyze_ticker.cache.get",
            new_callable=AsyncMock,
            return_value=forecasts,
        ) as cache_get:
            await services_ticker._forecast_ticker(baseline, research)
            await services_ticker._forecast_ticker(baseline, research)
        forecast_keys = [call.args[0] for call in cache_get.await_args_list]

        with patch(
            "app.services.msai_analyze_ticker.cache.get",
            new_callable=AsyncMock,
            return_value=recommendation,
        ) as cache_get:
            await services_ticker._recommend_ticker(
                baseline.snapshot,
                research,
                forecasts,
                holding_snapshot=holding_a,
            )
            await services_ticker._recommend_ticker(
                baseline.snapshot,
                research,
                forecasts,
                holding_snapshot=holding_b,
            )
        recommendation_keys = [call.args[0] for call in cache_get.await_args_list]
        return research_keys, forecast_keys, recommendation_keys

    research_keys, forecast_keys, recommendation_keys = asyncio.run(collect_keys())

    assert research_keys[0] == research_keys[1]
    assert forecast_keys[0] == forecast_keys[1]
    assert recommendation_keys[0] != recommendation_keys[1]


def test_unverified_source_is_retained_with_warning():
    result = ticker_fixtures.make_analysis(verified_reference=False)

    assert result.references[0].is_verified is False
    assert result.analysis_status == "CompleteWithWarnings"
    assert result.validation_warnings == ["1 cited research source(s) could not be provider-verified."]


def test_market_stage_caches_for_one_hour():
    baseline = ticker_fixtures.make_baseline()
    with (
        patch("app.services.msai_analyze_ticker.cache.get", new_callable=AsyncMock, return_value=None),
        patch("app.services.msai_analyze_ticker.cache.set", new_callable=AsyncMock) as cache_set,
        patch("app.services.msai_analyze_ticker._build_market_baseline", return_value=baseline),
    ):
        result = asyncio.run(services_ticker._get_market_baseline("NASDAQ:AAPL"))

    assert result == baseline
    assert cache_set.await_args.kwargs["ttl"] == 3600


def test_optional_benchmark_lookup_failure_is_non_fatal():
    data_gaps = []
    with patch(
        "app.services.msai_analyze_ticker.yfutils.lookup_index_yf_static_symbol",
        side_effect=ValueError("missing metadata"),
    ):
        result = services_ticker._load_optional_relative_return_for_ticker(
            object(),
            use_peer=False,
            label="market benchmark",
            data_gaps=data_gaps,
        )

    assert result is None
    assert data_gaps == ["A representative market benchmark is unavailable."]


def test_ai_stages_and_final_result_cache_for_one_hour():
    baseline = ticker_fixtures.make_baseline()
    research = ticker_fixtures.make_research()
    forecasts = ticker_fixtures.make_forecasts()
    recommendation = ticker_fixtures.make_recommendation()
    responses = [
        ai_helper.LLMResponse(completion="{}", citation_urls=[ticker_fixtures.SOURCE_URL]),
        ai_helper.LLMResponse(completion="{}"),
        ai_helper.LLMResponse(completion="{}"),
    ]

    async def execute():
        with (
            patch("app.services.msai_analyze_ticker.cache.get", new_callable=AsyncMock, return_value=None),
            patch("app.services.msai_analyze_ticker.cache.set", new_callable=AsyncMock) as cache_set,
            patch(
                "app.services.msai_analyze_ticker._get_market_baseline", new_callable=AsyncMock, return_value=baseline
            ),
            patch(
                "app.services.msai_analyze_ticker._finalize_research_references",
                return_value=research,
            ),
            patch(
                "app.services.msai_analyze_ticker._repair_research_references",
                return_value=research,
            ),
            patch(
                "app.services.msai_analyze_ticker._TickerResearchResponse.model_validate_json",
                return_value=type("Research", (), {"symbol": "NASDAQ:AAPL"})(),
            ),
            patch(
                "app.services.msai_analyze_ticker._finalize_forecasts",
                return_value=forecasts,
            ),
            patch(
                "app.services.msai_analyze_ticker._TickerForecastResponse.model_validate_json",
                return_value=type("Forecast", (), {"symbol": "NASDAQ:AAPL"})(),
            ),
            patch(
                "app.services.msai_analyze_ticker._finalize_recommendation",
                return_value=recommendation,
            ),
            patch(
                "app.services.msai_analyze_ticker._TickerRecommendationDraft.model_validate_json",
                return_value=object(),
            ),
            patch(
                "app.services.msai_analyze_ticker.ai_helper.ai_exec_task",
                new_callable=AsyncMock,
                side_effect=responses,
            ),
        ):
            result = await services_ticker.ai_analyze_ticker(symbol="NASDAQ:AAPL")
        return result, cache_set

    result, cache_set = asyncio.run(execute())

    assert result.symbol == "NASDAQ:AAPL"
    assert cache_set.await_count == 4
    assert {call.kwargs["ttl"] for call in cache_set.await_args_list} == {3600}


def test_cached_final_result_skips_all_stages():
    cached = ticker_fixtures.make_analysis()
    with (
        patch(
            "app.services.msai_analyze_ticker._get_market_baseline",
            new_callable=AsyncMock,
            return_value=ticker_fixtures.make_baseline(),
        ),
        patch("app.services.msai_analyze_ticker.cache.get", new_callable=AsyncMock, return_value=cached),
        patch("app.services.msai_analyze_ticker._research_ticker", new_callable=AsyncMock) as research,
    ):
        result = asyncio.run(services_ticker.ai_analyze_ticker(symbol="NASDAQ:AAPL"))

    assert result == cached
    research.assert_not_awaited()
