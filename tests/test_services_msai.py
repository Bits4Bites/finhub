"""Documentation-driven black-box tests for ticker analysis."""

import asyncio
from contextlib import contextmanager
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from app.models import ai_ticker as models_ai_ticker
from app.schemas import ai_ticker as schemas_ticker
from app.services import ai_helper
from app.services import msai_analyze_ticker as service
from tests import ai_service_fixtures, ticker_fixtures


def _analyze(
    *,
    symbol: str = "  nasdaq:aapl  ",
    holding: schemas_ticker.TickerHoldingInput | None = None,
):
    return asyncio.run(
        service.ai_analyze_ticker(
            symbol=symbol,
            current_holding=holding,
        )
    )


@contextmanager
def _dependencies(
    *,
    market: ticker_fixtures.MarketBoundary,
    ai: ai_service_fixtures.OpaqueAIQueue,
    cache,
):
    with (
        patch.object(service.yf, "Ticker", side_effect=market),
        patch.object(service.yfutils, "lookup_index_yf_static_symbol", return_value=None),
        patch.object(service.yfutils, "lookup_peer_yf_static_symbol", return_value=None),
        patch.object(service.cache, "get", side_effect=cache.get),
        patch.object(service.cache, "set", side_effect=cache.set),
        patch.object(service.ai_helper, "ai_exec_task", new=ai),
    ):
        yield


def test_invalid_symbols_raise_documented_input_error():
    with pytest.raises(service.TickerInputError):
        _analyze(symbol="   ")

    cache = ai_service_fixtures.ExpiringCache()
    market = ticker_fixtures.MarketBoundary(quote_type="OPTION")
    ai = ai_service_fixtures.OpaqueAIQueue()
    with (
        _dependencies(market=market, ai=ai, cache=cache),
        pytest.raises(service.TickerInputError),
    ):
        _analyze()


@pytest.mark.parametrize(
    "holding_data",
    [
        {"num_shares": float("nan"), "avg_price": 100},
        {"num_shares": 1, "avg_price": float("-inf")},
    ],
)
def test_non_finite_holding_values_are_rejected_by_public_input_model(holding_data):
    with pytest.raises(ValidationError):
        schemas_ticker.TickerHoldingInput.model_validate(holding_data)


def test_market_provider_failure_is_mapped_to_verification_error():
    cache = ai_service_fixtures.ExpiringCache()

    def unavailable_market(_symbol: str):
        raise OSError("market unavailable")

    with (
        patch.object(service.yf, "Ticker", side_effect=unavailable_market),
        patch.object(service.cache, "get", side_effect=cache.get),
        pytest.raises(service.TickerVerificationError),
    ):
        _analyze()


def test_returns_four_ordered_horizons_and_holding_only_changes_holding_semantics():
    cache = ai_service_fixtures.ExpiringCache()
    market = ticker_fixtures.MarketBoundary()
    ai = ai_service_fixtures.OpaqueAIQueue(ticker_fixtures.make_ai_responses(recommendation_count=2))
    holding = schemas_ticker.TickerHoldingInput(num_shares=10, avg_price=80)

    with _dependencies(market=market, ai=ai, cache=cache):
        new_position = _analyze()
        existing_holding = _analyze(holding=holding)

    assert [forecast.horizon for forecast in new_position.forecasts] == list(ticker_fixtures.HORIZONS)
    assert new_position.analysis_status == "Complete"
    assert new_position.recommendation.scope == "NewPosition"
    assert new_position.holding_snapshot is None

    assert existing_holding.recommendation.scope == "ExistingHolding"
    assert existing_holding.holding_snapshot is not None
    assert existing_holding.holding_snapshot.cost_basis == 800
    assert existing_holding.holding_snapshot.market_value == 1_000
    assert existing_holding.holding_snapshot.unrealized_profit_loss == 200
    assert existing_holding.holding_snapshot.unrealized_return_pct == 25

    assert existing_holding.research == new_position.research
    assert existing_holding.forecasts == new_position.forecasts
    assert existing_holding.references == new_position.references


def test_unmatched_provider_citations_are_retained_as_unverified_warnings():
    cache = ai_service_fixtures.ExpiringCache()
    market = ticker_fixtures.MarketBoundary()
    ai = ai_service_fixtures.OpaqueAIQueue(ticker_fixtures.make_ai_responses(verified=False))

    with _dependencies(market=market, ai=ai, cache=cache):
        result = _analyze()

    assert result.analysis_status == "CompleteWithWarnings"
    assert result.validation_warnings
    assert result.references
    assert all(reference.is_verified is False for reference in result.references)


def test_repeated_public_call_uses_validated_cache_when_dependencies_are_unavailable():
    cache = ai_service_fixtures.ExpiringCache()
    market = ticker_fixtures.MarketBoundary()
    ai = ai_service_fixtures.OpaqueAIQueue(ticker_fixtures.make_ai_responses())

    with _dependencies(market=market, ai=ai, cache=cache):
        first = _analyze()
        market.available = False
        second = _analyze()

    assert second == first


def test_documented_one_hour_cache_expiry_requires_dependencies_again():
    clock = ai_service_fixtures.ManualClock()
    cache = ai_service_fixtures.ExpiringCache(clock)
    market = ticker_fixtures.MarketBoundary()
    ai = ai_service_fixtures.OpaqueAIQueue(ticker_fixtures.make_ai_responses())

    with _dependencies(market=market, ai=ai, cache=cache):
        first = _analyze()
        market.available = False
        clock.advance(60 * 60 - 1)
        assert _analyze() == first
        clock.advance(1)
        with pytest.raises(service.TickerVerificationError):
            _analyze()


def test_ai_error_response_raises_documented_analysis_error():
    cache = ai_service_fixtures.ExpiringCache()
    market = ticker_fixtures.MarketBoundary()
    ai = ai_service_fixtures.OpaqueAIQueue(
        [
            ai_helper.LLMResponse(
                is_error=True,
                completion="provider rejected the request",
                error_msg="provider rejected the request",
            )
        ]
    )

    with (
        _dependencies(market=market, ai=ai, cache=cache),
        pytest.raises(service.TickerAnalysisAIError),
    ):
        _analyze()


def test_rate_limit_failure_propagates():
    cache = ai_service_fixtures.ExpiringCache()
    market = ticker_fixtures.MarketBoundary()
    failure = ai_helper.LLMRateLimitError("retry budget exhausted")
    ai = ai_service_fixtures.OpaqueAIQueue([failure])

    with (
        _dependencies(market=market, ai=ai, cache=cache),
        pytest.raises(ai_helper.LLMRateLimitError) as error_info,
    ):
        _analyze()

    assert error_info.value is failure


def test_malformed_ai_result_raises_analysis_error():
    cache = ai_service_fixtures.ExpiringCache()
    market = ticker_fixtures.MarketBoundary()
    ai = ai_service_fixtures.OpaqueAIQueue([ai_helper.LLMResponse(completion="{not-json")])

    with (
        _dependencies(market=market, ai=ai, cache=cache),
        pytest.raises(service.TickerAnalysisAIError),
    ):
        _analyze()


def test_opaque_invalid_market_cache_raises_verification_error():
    cache = ai_service_fixtures.InvalidCache(object())
    market = ticker_fixtures.MarketBoundary()
    ai = ai_service_fixtures.OpaqueAIQueue()

    with (
        _dependencies(market=market, ai=ai, cache=cache),
        pytest.raises(service.TickerVerificationError),
    ):
        _analyze()


def test_opaque_invalid_final_cache_raises_analysis_error():
    cache = ai_service_fixtures.ExpiringCache()
    market = ticker_fixtures.MarketBoundary()
    ai = ai_service_fixtures.OpaqueAIQueue(ticker_fixtures.make_ai_responses())

    with _dependencies(market=market, ai=ai, cache=cache):
        _analyze()
        cache.corrupt_cached_model(models_ai_ticker.TickerAnalysis, object())
        with pytest.raises(service.TickerAnalysisAIError):
            _analyze()


def test_cache_backend_failure_is_propagated():
    failure = ConnectionError("cache unavailable")

    async def unavailable_cache(_key: str):
        raise failure

    with (
        patch.object(service.cache, "get", side_effect=unavailable_cache),
        pytest.raises(ConnectionError) as error_info,
    ):
        _analyze()

    assert error_info.value is failure
