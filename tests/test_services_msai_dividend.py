"""Documentation-driven black-box tests for dividend-event analysis."""

import asyncio
import copy
import json
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from app.models import events_div as models_dividends
from app.services import ai_helper
from app.services import msai_analyze_div_event as service
from app.utils import ai_reference
from tests import ai_service_fixtures

_SOURCE_URL = "https://example.com/dividend-announcement"
_SOURCE_ID = ai_reference.generate_source_id(_SOURCE_URL)
_LONDON_TZ = ZoneInfo("Europe/London")


def _future_ex_date() -> date:
    return datetime.now(_LONDON_TZ).date() + timedelta(days=30)


def _market_history(*, sessions: int = 250) -> pd.DataFrame:
    end = datetime.now(_LONDON_TZ).date() - timedelta(days=2)
    dates = pd.date_range(end=end, periods=sessions, freq="D", tz=_LONDON_TZ)
    history = pd.DataFrame(
        {
            "Open": np.full(sessions, 100.0),
            "High": np.full(sessions, 101.0),
            "Low": np.full(sessions, 99.0),
            "Close": np.full(sessions, 100.0),
            "Volume": np.full(sessions, 100_000.0),
            "Dividends": np.zeros(sessions),
        },
        index=dates,
    )
    for position in (30, 80, 130, 180):
        if position >= sessions - 1:
            continue
        history.iloc[position, history.columns.get_loc("Open")] = 99.0
        history.iloc[position, history.columns.get_loc("Close")] = 98.5
        history.iloc[position, history.columns.get_loc("Low")] = 98.0
        history.iloc[position, history.columns.get_loc("Dividends")] = 2.0
        history.iloc[position + 1, history.columns.get_loc("Close")] = 100.0
    return history


def _ticker(*, quote_type: str = "EQUITY", sessions: int = 250) -> MagicMock:
    ticker = MagicMock()
    ticker.info = {
        "quoteType": quote_type,
        "symbol": "ABC.L",
        "fullExchangeName": "LSE",
        "exchangeTimezoneName": "Europe/London",
        "country": "United Kingdom",
        "currency": "GBP",
        "longName": "Example Holdings plc",
        "regularMarketPrice": 100.0,
        "marketState": "CLOSED",
        "beta": 1.1,
        "sector": "Technology",
        "industry": "Software",
    }
    ticker.history.return_value = _market_history(sessions=sessions)
    return ticker


def _research_payload() -> dict[str, object]:
    section = {
        "facts": [
            {
                "text": "The issuer announced the dividend terms.",
                "reference_ids": [_SOURCE_URL],
            }
        ],
        "data_gaps": [],
        "reference_ids": [_SOURCE_URL],
    }
    return {
        "symbol": "ABC.L",
        "as_of": datetime.now(UTC).isoformat(),
        "dividend_terms": copy.deepcopy(section),
        "issuer_outlook": copy.deepcopy(section),
        "event_risks": copy.deepcopy(section),
        "market_context": copy.deepcopy(section),
        "references": [
            {
                "id": _SOURCE_URL,
                "title": "Dividend announcement",
                "publisher": "Example Exchange",
                "source_type": "Exchange",
                "published_at": None,
                "accessed_at": None,
                "url": _SOURCE_URL,
            }
        ],
    }


def _ineligible_strategy(name: str, *, warnings: bool) -> dict[str, object]:
    reference_ids = [_SOURCE_ID]
    if warnings:
        reference_ids.append("unsupported-source")
    return {
        "strategy": name,
        "eligibility": "InsufficientData",
        "ineligibility_reason": "The available evidence does not support a reliable estimate.",
        "success_probability": None,
        "expected_entry_price": None,
        "expected_exit_price": None,
        "expected_profit_loss_per_share": None,
        "break_even_price": None,
        "recovery_days": None,
        "confidence": 25,
        "risk": 70,
        "rationale": "More evidence is required.",
        "risk_factors": ["Market prices may move unexpectedly."],
        "assumptions": [],
        "data_gaps": ["Strategy estimates are unavailable."],
        "reference_ids": reference_ids,
    }


def _assessment_payload(*, warnings: bool = False) -> dict[str, object]:
    comparison_reference_ids = [_SOURCE_ID]
    if warnings:
        comparison_reference_ids.append("unsupported-source")
    return {
        "symbol": "ABC.L",
        "as_of": datetime.now(UTC).isoformat(),
        "overall_data_quality": "High",
        "evidence_adjusted_ex_date_close_drop": None,
        "evidence_adjusted_pre_ex_close_recovery": None,
        "evidence_adjusted_capture_break_even_recovery": None,
        "evidence_adjusted_discount_break_even_recovery": None,
        "dividend_capture": _ineligible_strategy("DividendCapture", warnings=warnings),
        "post_dividend_discount": _ineligible_strategy("PostDividendDiscount", warnings=warnings),
        "comparison_rationale": "The strategies cannot be compared reliably.",
        "comparison_reference_ids": comparison_reference_ids,
    }


def _research_response(*, verified: bool = True) -> ai_helper.LLMResponse:
    return ai_helper.LLMResponse(
        completion=json.dumps(_research_payload()),
        citation_urls=[_SOURCE_URL] if verified else [],
    )


def _assessment_response(*, warnings: bool = False) -> ai_helper.LLMResponse:
    return ai_helper.LLMResponse(completion=json.dumps(_assessment_payload(warnings=warnings)))


def _ai_error_response() -> ai_helper.LLMResponse:
    return ai_helper.LLMResponse(
        is_error=True,
        completion="provider rejected the request",
        error_msg="provider rejected the request",
    )


def _analyze(**overrides):
    arguments = {
        "symbol": "LSE:ABC",
        "ex_date": _future_ex_date(),
        "dividend_amount": 2.0,
    }
    arguments.update(overrides)
    return asyncio.run(service.ai_analyze_div_event(**arguments))


@contextmanager
def _dependencies(
    *,
    ticker: MagicMock,
    ai: ai_service_fixtures.OpaqueAIQueue,
    cache,
):
    with (
        patch.object(service.yf, "Ticker", return_value=ticker),
        patch.object(service.yfutils, "lookup_index_yf_static_symbol", return_value=None),
        patch.object(service.yfutils, "lookup_peer_yf_static_symbol", return_value=None),
        patch.object(service.cache, "get", side_effect=cache.get),
        patch.object(service.cache, "set", side_effect=cache.set),
        patch.object(service.ai_helper, "ai_exec_task", new=ai),
    ):
        yield


@pytest.mark.parametrize(
    "overrides",
    [
        {"symbol": "   "},
        {"symbol": "A" * 129},
        {"ex_date": datetime.now(UTC)},
        {"dividend_amount": 0.0},
        {"dividend_amount": -1.0},
        {"dividend_amount": float("inf")},
        {"dividend_amount": float("nan")},
        {"dividend_amount": float("-inf")},
        {"holding_period_days": 0},
        {"holding_period_days": 366},
    ],
)
def test_invalid_direct_inputs_raise_documented_input_error(overrides):
    with pytest.raises(service.DividendEventInputError):
        _analyze(**overrides)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("dividend_capture_per_share", -0.01),
        ("dividend_capture_per_share", float("nan")),
        ("post_dividend_discount_per_share", float("-inf")),
        ("post_dividend_discount_per_share", float("inf")),
    ],
)
def test_invalid_transaction_costs_are_rejected_by_public_model(field, value):
    values = {
        "dividend_capture_per_share": 0.0,
        "post_dividend_discount_per_share": 0.0,
    }
    values[field] = value

    with pytest.raises(ValidationError):
        models_dividends.DividendTransactionCosts.model_validate(values)


def test_unsupported_security_type_raises_documented_input_error():
    with (
        patch.object(service.yf, "Ticker", return_value=_ticker(quote_type="CRYPTOCURRENCY")),
        pytest.raises(service.DividendEventInputError),
    ):
        _analyze()


def test_89_sessions_are_insufficient_but_90_sessions_are_accepted():
    with (
        patch.object(service.yf, "Ticker", return_value=_ticker(sessions=89)),
        pytest.raises(service.DividendEventInsufficientDataError),
    ):
        _analyze()

    cache = ai_service_fixtures.ExpiringCache()
    ai = ai_service_fixtures.OpaqueAIQueue([_research_response(), _assessment_response()])
    with _dependencies(ticker=_ticker(sessions=90), ai=ai, cache=cache):
        result = _analyze()

    assert result.analysis_status == "Complete"
    assert result.historical_baseline.sample_count >= 1


def test_complete_analysis_preserves_baseline_and_is_reused_when_ai_is_unavailable():
    cache = ai_service_fixtures.ExpiringCache()
    ai = ai_service_fixtures.OpaqueAIQueue([_research_response(), _assessment_response()])
    with _dependencies(ticker=_ticker(), ai=ai, cache=cache):
        first = _analyze(holding_period_days=35)
        second = _analyze(holding_period_days=35)

    assert second == first
    assert first.analysis_status == "Complete"
    assert first.event.symbol == "ABC.L"
    assert first.event.holding_period_days == 35
    assert first.historical_baseline.sample_count == 4
    assert first.recommendation is not None
    assert first.recommendation.outcome == "InsufficientInsights"
    assert first.evidence_adjusted_ex_date_close_drop is None
    assert first.evidence_adjusted_pre_ex_close_recovery is None
    assert first.evidence_adjusted_capture_break_even_recovery is None
    assert first.evidence_adjusted_discount_break_even_recovery is None
    assert first.references[0].is_verified is True


def test_unmatched_provider_citations_are_retained_and_lower_data_quality():
    cache = ai_service_fixtures.ExpiringCache()
    ai = ai_service_fixtures.OpaqueAIQueue([_research_response(verified=False), _assessment_response()])
    with _dependencies(ticker=_ticker(), ai=ai, cache=cache):
        result = _analyze()

    assert result.analysis_status == "Complete"
    assert result.overall_data_quality == "Low"
    assert result.references
    assert all(reference.is_verified is False for reference in result.references)


def test_supported_results_with_repaired_references_return_warnings():
    cache = ai_service_fixtures.ExpiringCache()
    ai = ai_service_fixtures.OpaqueAIQueue([_research_response(), _assessment_response(warnings=True)])
    with _dependencies(ticker=_ticker(), ai=ai, cache=cache):
        result = _analyze()

    assert result.analysis_status == "CompleteWithWarnings"
    assert result.historical_baseline.sample_count == 4
    assert result.validation_warnings
    assert result.dividend_capture is not None
    assert result.dividend_capture.reference_ids == [_SOURCE_ID]
    assert result.post_dividend_discount is not None
    assert result.post_dividend_discount.reference_ids == [_SOURCE_ID]


def test_research_failure_returns_and_caches_failed_analysis_with_baseline():
    cache = ai_service_fixtures.ExpiringCache()
    ai = ai_service_fixtures.OpaqueAIQueue([_ai_error_response()])
    with _dependencies(ticker=_ticker(), ai=ai, cache=cache):
        first = _analyze()
        second = _analyze()

    assert second == first
    assert first.analysis_status == "Failed"
    assert first.failure_reason
    assert first.historical_baseline.sample_count == 4
    assert first.research is None
    assert first.dividend_capture is None
    assert first.recommendation is None


def test_assessment_failure_preserves_research_and_deterministic_baseline():
    cache = ai_service_fixtures.ExpiringCache()
    ai = ai_service_fixtures.OpaqueAIQueue([_research_response(), _ai_error_response()])
    with _dependencies(ticker=_ticker(), ai=ai, cache=cache):
        result = _analyze()

    assert result.analysis_status == "Failed"
    assert result.failure_reason
    assert result.historical_baseline.sample_count == 4
    assert result.research is not None
    assert result.references
    assert result.dividend_capture is None
    assert result.recommendation is None


def test_failed_analysis_cache_expires_after_documented_five_minutes():
    clock = ai_service_fixtures.ManualClock()
    cache = ai_service_fixtures.ExpiringCache(clock)
    rate_limit = ai_helper.LLMRateLimitError("AI boundary unavailable")
    ai = ai_service_fixtures.OpaqueAIQueue(
        [_ai_error_response()],
        empty_exception=rate_limit,
    )
    with _dependencies(ticker=_ticker(), ai=ai, cache=cache):
        first = _analyze()
        clock.advance(5 * 60 - 1)
        assert _analyze() == first
        clock.advance(1)
        with pytest.raises(ai_helper.LLMRateLimitError) as error_info:
            _analyze()

    assert error_info.value is rate_limit


def test_opaque_invalid_cached_analysis_raises_runtime_error():
    cache = ai_service_fixtures.InvalidCache(object())
    ai = ai_service_fixtures.OpaqueAIQueue()
    with (
        _dependencies(ticker=_ticker(), ai=ai, cache=cache),
        pytest.raises(RuntimeError),
    ):
        _analyze()


def test_rate_limit_failure_is_not_cached_and_a_later_public_call_can_recover():
    cache = ai_service_fixtures.ExpiringCache()
    failure = ai_helper.LLMRateLimitError("retry budget exhausted")
    ai = ai_service_fixtures.OpaqueAIQueue([failure, _research_response(), _assessment_response()])
    with _dependencies(ticker=_ticker(), ai=ai, cache=cache):
        with pytest.raises(ai_helper.LLMRateLimitError) as error_info:
            _analyze()
        recovered = _analyze()

    assert error_info.value is failure
    assert recovered.analysis_status == "Complete"
    assert recovered.historical_baseline.sample_count == 4
