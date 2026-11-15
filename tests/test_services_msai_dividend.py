import asyncio
import copy
import json
from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from app.models import events_dividends as models_dividends
from app.services import ai_helper
from app.services import msai_analyze_div_event as service
from app.utils import ai_reference

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
        if position >= sessions - 30:
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


def _research_response() -> ai_helper.LLMResponse:
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
    payload = {
        "symbol": "ABC.L",
        "as_of": datetime.now(UTC).isoformat(),
        "dividend_terms": section,
        "issuer_outlook": section,
        "event_risks": section,
        "market_context": section,
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
    return ai_helper.LLMResponse(
        completion=json.dumps(payload),
        citation_urls=[_SOURCE_URL],
    )


def _ineligible_strategy(name: str) -> dict[str, object]:
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
        "reference_ids": [_SOURCE_ID],
    }


def _assessment_response() -> ai_helper.LLMResponse:
    payload = {
        "symbol": "ABC.L",
        "as_of": datetime.now(UTC).isoformat(),
        "overall_data_quality": "High",
        "evidence_adjusted_ex_date_close_drop": None,
        "evidence_adjusted_pre_ex_close_recovery": None,
        "evidence_adjusted_capture_break_even_recovery": None,
        "evidence_adjusted_discount_break_even_recovery": None,
        "dividend_capture": _ineligible_strategy("DividendCapture"),
        "post_dividend_discount": _ineligible_strategy("PostDividendDiscount"),
        "comparison_rationale": "The strategies cannot be compared reliably.",
        "comparison_reference_ids": [_SOURCE_ID],
    }
    return ai_helper.LLMResponse(completion=json.dumps(payload))


def _run_analysis(**overrides):
    arguments = {
        "symbol": "LSE:ABC",
        "ex_date": _future_ex_date(),
        "dividend_amount": 2.0,
    }
    arguments.update(overrides)
    return asyncio.run(service.ai_analyze_div_event(**arguments))


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"symbol": "   "}, "Symbol is required"),
        ({"symbol": "A" * 129}, "must not exceed 128"),
        (
            {"ex_date": datetime.now(UTC)},
            "Ex-dividend date must be a date",
        ),
        ({"dividend_amount": 0.0}, "positive finite number"),
        ({"dividend_amount": float("inf")}, "positive finite number"),
        ({"holding_period_days": 0}, "between 1 and 365"),
        ({"holding_period_days": 366}, "between 1 and 365"),
    ],
)
def test_rejects_direct_input_boundaries_before_calling_providers(overrides, message):
    with (
        patch.object(service.yf, "Ticker") as ticker_factory,
        pytest.raises(service.DividendEventInputError, match=message),
    ):
        _run_analysis(**overrides)

    ticker_factory.assert_not_called()


@pytest.mark.parametrize(
    "costs",
    [
        models_dividends.DividendTransactionCosts.model_construct(
            dividend_capture_per_share=-0.01,
            post_dividend_discount_per_share=0.0,
        ),
        models_dividends.DividendTransactionCosts.model_construct(
            dividend_capture_per_share=0.0,
            post_dividend_discount_per_share=float("nan"),
        ),
    ],
)
def test_rejects_invalid_transaction_costs_even_when_model_validation_is_bypassed(costs):
    with pytest.raises(
        service.DividendEventInputError,
        match="Transaction costs must be non-negative finite numbers",
    ):
        _run_analysis(transaction_costs=costs)


def test_rejects_unsupported_security_type():
    with (
        patch.object(service.yf, "Ticker", return_value=_ticker(quote_type="CRYPTOCURRENCY")),
        pytest.raises(
            service.DividendEventInputError,
            match="Unsupported or unknown asset type",
        ),
    ):
        _run_analysis()


def test_symbol_length_bound_applies_after_surrounding_whitespace_is_removed():
    with (
        patch.object(service.yf, "Ticker", return_value=_ticker(quote_type="CRYPTOCURRENCY")),
        pytest.raises(
            service.DividendEventInputError,
            match="Unsupported or unknown asset type",
        ),
    ):
        _run_analysis(symbol=f" {'A' * 128} ")


def test_requires_sufficient_complete_market_history():
    with (
        patch.object(service.yf, "Ticker", return_value=_ticker(sessions=89)),
        pytest.raises(
            service.DividendEventInsufficientDataError,
            match="At least 90 complete market sessions",
        ),
    ):
        _run_analysis()


def test_returns_complete_analysis_and_reuses_validated_cache():
    ticker = _ticker()
    cache_entries: dict[str, object] = {}

    async def cache_get(key):
        return copy.deepcopy(cache_entries.get(key))

    async def cache_set(key, value, *, ttl):
        assert ttl > 0
        cache_entries[key] = copy.deepcopy(value)
        return True

    with (
        patch.object(service.yf, "Ticker", return_value=ticker) as ticker_factory,
        patch.object(service.cache, "get", side_effect=cache_get),
        patch.object(service.cache, "set", side_effect=cache_set),
        patch.object(
            service.ai_helper,
            "ai_exec_task",
            new_callable=AsyncMock,
            side_effect=[_research_response(), _assessment_response()],
        ) as ai_exec,
    ):
        first = _run_analysis(holding_period_days=35)
        second = _run_analysis(holding_period_days=35)

    assert first == second
    assert first.analysis_status == "Complete"
    assert first.event.symbol == "ABC.L"
    assert first.event.holding_period_days == 35
    assert first.historical_baseline.sample_count == 4
    assert first.recommendation is not None
    assert first.recommendation.outcome == "InsufficientInsights"
    assert first.references[0].is_verified is True
    assert ai_exec.await_count == 2
    assert ticker_factory.call_count == 2
    ticker_factory.assert_any_call("ABC.L")


def test_recoverable_ai_failure_preserves_deterministic_baseline_and_is_cached_briefly():
    cache_set = AsyncMock(return_value=True)

    with (
        patch.object(service.yf, "Ticker", return_value=_ticker()),
        patch.object(service.cache, "get", new_callable=AsyncMock, return_value=None),
        patch.object(service.cache, "set", cache_set),
        patch.object(
            service.ai_helper,
            "ai_exec_task",
            new_callable=AsyncMock,
            return_value=ai_helper.LLMResponse(
                is_error=True,
                error_msg="provider rejected the request",
            ),
        ),
    ):
        result = _run_analysis()

    assert result.analysis_status == "Failed"
    assert result.failure_reason == "Dividend research failed"
    assert result.historical_baseline.sample_count == 4
    assert result.research is None
    assert result.dividend_capture is None
    cache_set.assert_awaited_once()
    assert cache_set.await_args.kwargs["ttl"] == 5 * 60


def test_rate_limit_failure_propagates_without_caching_failed_analysis():
    cache_set = AsyncMock(return_value=True)

    with (
        patch.object(service.yf, "Ticker", return_value=_ticker()),
        patch.object(service.cache, "get", new_callable=AsyncMock, return_value=None),
        patch.object(service.cache, "set", cache_set),
        patch.object(
            service.ai_helper,
            "ai_exec_task",
            new_callable=AsyncMock,
            side_effect=ai_helper.LLMRateLimitError("retry budget exhausted"),
        ),
        pytest.raises(ai_helper.LLMRateLimitError, match="retry budget exhausted"),
    ):
        _run_analysis()

    cache_set.assert_not_awaited()


def test_rejects_invalid_cached_analysis():
    with (
        patch.object(service.yf, "Ticker", return_value=_ticker()),
        patch.object(
            service.cache,
            "get",
            new_callable=AsyncMock,
            return_value=object(),
        ),
        pytest.raises(
            RuntimeError,
            match="Dividend analysis cache contains an invalid value",
        ),
    ):
        _run_analysis()
