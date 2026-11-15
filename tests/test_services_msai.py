"""Black-box tests for the public ticker-analysis service."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from app.schemas import ai_ticker as schemas_ticker
from app.services import ai_helper
from app.services import msai_analyze_ticker as service
from tests import ticker_fixtures


def _run_analysis(*, holding: schemas_ticker.TickerHoldingInput | None = None):
    return asyncio.run(
        service.ai_analyze_ticker(
            symbol="  nasdaq:aapl  ",
            current_holding=holding,
        )
    )


def test_rejects_blank_symbol_before_market_or_cache_access():
    with (
        patch.object(service.cache, "get", new_callable=AsyncMock) as cache_get,
        patch.object(service.yf, "Ticker") as ticker_factory,
        pytest.raises(service.TickerInputError, match="Ticker symbol is required"),
    ):
        asyncio.run(service.ai_analyze_ticker(symbol="   "))

    cache_get.assert_not_awaited()
    ticker_factory.assert_not_called()


def test_rejects_unsupported_security_type_from_market_provider():
    ticker = MagicMock()
    ticker.info = {
        "quoteType": "OPTION",
        "symbol": "AAPL",
        "exchange": "NASDAQ",
    }

    with (
        patch.object(service.cache, "get", new_callable=AsyncMock, return_value=None),
        patch.object(service.yf, "Ticker", return_value=ticker),
        pytest.raises(
            service.TickerInputError,
            match="unsupported security type",
        ),
    ):
        asyncio.run(service.ai_analyze_ticker(symbol="NASDAQ:AAPL"))


def test_maps_market_provider_failure_to_verification_error():
    ticker = MagicMock()
    type(ticker).info = PropertyMock(side_effect=OSError("provider unavailable"))

    with (
        patch.object(service.cache, "get", new_callable=AsyncMock, return_value=None),
        patch.object(service.yf, "Ticker", return_value=ticker),
        pytest.raises(
            service.TickerVerificationError,
            match="market-data verification failed",
        ) as error_info,
    ):
        asyncio.run(service.ai_analyze_ticker(symbol="NASDAQ:AAPL"))

    assert isinstance(error_info.value.__cause__, OSError)


@pytest.mark.parametrize(
    ("holding", "expected_scope"),
    [
        (None, "NewPosition"),
        (
            schemas_ticker.TickerHoldingInput(num_shares=10, avg_price=80),
            "ExistingHolding",
        ),
    ],
)
def test_returns_analysis_with_optional_holding_context(holding, expected_scope):
    baseline = ticker_fixtures.make_baseline()
    research = ticker_fixtures.make_research()
    forecasts = ticker_fixtures.make_forecasts()
    recommendation = ticker_fixtures.make_recommendation(holding=holding is not None)
    cache_values = iter(
        [
            baseline.model_dump(mode="json"),
            None,
            research.model_dump(mode="json"),
            forecasts.model_dump(mode="json"),
            recommendation.model_dump(mode="json"),
        ]
    )
    cache_set = AsyncMock(return_value=True)

    with (
        patch.object(
            service.cache,
            "get",
            new_callable=AsyncMock,
            side_effect=lambda _key: next(cache_values),
        ),
        patch.object(service.cache, "set", cache_set),
        patch.object(service.yf, "Ticker") as ticker_factory,
        patch.object(
            service.ai_helper,
            "ai_exec_task",
            new_callable=AsyncMock,
        ) as ai_exec,
    ):
        result = _run_analysis(holding=holding)

    assert result.symbol == "NASDAQ:AAPL"
    assert result.analysis_status == "Complete"
    assert result.recommendation.scope == expected_scope
    if holding is None:
        assert result.holding_snapshot is None
    else:
        assert result.holding_snapshot is not None
        assert result.holding_snapshot.num_shares == 10
        assert result.holding_snapshot.avg_price == 80
        assert result.holding_snapshot.cost_basis == 800
        assert result.holding_snapshot.market_value == 1_000
        assert result.holding_snapshot.unrealized_profit_loss == 200
        assert result.holding_snapshot.unrealized_return_pct == 25
    cache_set.assert_awaited_once()
    assert cache_set.await_args.kwargs["ttl"] == 60 * 60
    ticker_factory.assert_not_called()
    ai_exec.assert_not_awaited()


def test_maps_ai_provider_failure_to_analysis_error():
    baseline = ticker_fixtures.make_baseline()
    cache_values = iter([baseline.model_dump(mode="json"), None, None])

    with (
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
            return_value=ai_helper.LLMResponse(
                is_error=True,
                error_msg="provider rejected the request",
            ),
        ),
        pytest.raises(
            service.TickerAnalysisAIError,
            match="Ticker research failed",
        ),
    ):
        _run_analysis()


def test_rate_limit_failure_propagates_from_ai_stage():
    baseline = ticker_fixtures.make_baseline()
    cache_values = iter([baseline.model_dump(mode="json"), None, None])

    with (
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
            side_effect=ai_helper.LLMRateLimitError("retry budget exhausted"),
        ),
        pytest.raises(ai_helper.LLMRateLimitError, match="retry budget exhausted"),
    ):
        _run_analysis()


def test_rejects_invalid_market_baseline_cache_value():
    with (
        patch.object(
            service.cache,
            "get",
            new_callable=AsyncMock,
            return_value={"not": "a market baseline"},
        ),
        pytest.raises(
            service.TickerVerificationError,
            match="market cache contains an invalid value",
        ),
    ):
        _run_analysis()


def test_rejects_invalid_final_analysis_cache_value():
    baseline = ticker_fixtures.make_baseline()
    cache_values = iter(
        [
            baseline.model_dump(mode="json"),
            {"not": "a ticker analysis"},
        ]
    )

    with (
        patch.object(
            service.cache,
            "get",
            new_callable=AsyncMock,
            side_effect=lambda _key: next(cache_values),
        ),
        pytest.raises(
            service.TickerAnalysisAIError,
            match="analysis cache contains an invalid value",
        ),
    ):
        _run_analysis()


def test_propagates_cache_backend_failure():
    with (
        patch.object(
            service.cache,
            "get",
            new_callable=AsyncMock,
            side_effect=ConnectionError("cache unavailable"),
        ),
        pytest.raises(ConnectionError, match="cache unavailable"),
    ):
        _run_analysis()
