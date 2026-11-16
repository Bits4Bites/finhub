from unittest import mock

import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app
from app.models import ai_ticker as models_ticker
from app.services import ai_helper
from app.services import msai_analyze_ticker as services_ticker
from tests import ticker_fixtures

client = TestClient(app)


@pytest.fixture(autouse=True)
def disable_ai_proxy(monkeypatch):
    monkeypatch.setattr(config.settings_finhub_proxy, "proxy_mode", "None")
    monkeypatch.setattr(config.settings_finhub_proxy, "url_ai_task_node", "")


def _request_body(*, include_holding: bool = True) -> dict[str, object]:
    body: dict[str, object] = {"symbol": " nasdaq:aapl "}
    if include_holding:
        body["current_holding"] = {"num_shares": 10, "avg_price": 80}
    return body


async def _analysis_for_request(
    *,
    symbol: str,
    current_holding,
) -> models_ticker.TickerAnalysis:
    holding_snapshot = None
    if current_holding is not None:
        market_price = 100.0
        cost_basis = current_holding.num_shares * current_holding.avg_price
        market_value = current_holding.num_shares * market_price
        profit_loss = market_value - cost_basis
        holding_snapshot = models_ticker.TickerHoldingSnapshot(
            num_shares=current_holding.num_shares,
            avg_price=current_holding.avg_price,
            currency="USD",
            market_price=market_price,
            cost_basis=cost_basis,
            market_value=market_value,
            unrealized_profit_loss=profit_loss,
            unrealized_return_pct=profit_loss / cost_basis * 100,
            break_even_price=current_holding.avg_price,
        )

    analysis = ticker_fixtures.make_analysis(holding=holding_snapshot)
    analysis_data = analysis.model_dump(mode="python")
    analysis_data["symbol"] = symbol
    analysis_data["market_snapshot"]["symbol"] = symbol
    return models_ticker.TickerAnalysis.model_validate(analysis_data)


def test_sync_ticker_analysis_exposes_normalized_symbol_and_holding_snapshot():
    with mock.patch(
        "app.routers.ai_ticker.services_ticker.ai_analyze_ticker",
        new=_analysis_for_request,
    ):
        response = client.post("/ai/analyze_ticker", json=_request_body())

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["symbol"] == "NASDAQ:AAPL"
    assert data["market_snapshot"]["symbol"] == "NASDAQ:AAPL"
    assert data["holding_snapshot"] == {
        "num_shares": 10.0,
        "avg_price": 80.0,
        "currency": "USD",
        "market_price": 100.0,
        "cost_basis": 800.0,
        "market_value": 1000.0,
        "unrealized_profit_loss": 200.0,
        "unrealized_return_pct": 25.0,
        "break_even_price": 80.0,
    }
    assert data["recommendation"]["scope"] == "ExistingHolding"


def test_sync_ticker_analysis_omits_holding_snapshot_for_a_new_position():
    with mock.patch(
        "app.routers.ai_ticker.services_ticker.ai_analyze_ticker",
        new=_analysis_for_request,
    ):
        response = client.post(
            "/ai/analyze_ticker",
            json=_request_body(include_holding=False),
        )

    assert response.status_code == 200
    assert "holding_snapshot" not in response.json()["data"]
    assert response.json()["data"]["recommendation"]["scope"] == "NewPosition"


def test_sync_ticker_analysis_exposes_fixed_forecast_horizons_and_ordered_ranges():
    with mock.patch(
        "app.routers.ai_ticker.services_ticker.ai_analyze_ticker",
        new=_analysis_for_request,
    ):
        response = client.post(
            "/ai/analyze_ticker",
            json=_request_body(include_holding=False),
        )

    assert response.status_code == 200
    forecasts = response.json()["data"]["forecasts"]
    assert [
        (
            forecast["horizon"],
            forecast["horizon_days"],
            forecast["period_end"],
            forecast["expected_price_min"],
            forecast["expected_price_max"],
        )
        for forecast in forecasts
    ] == [
        ("OneWeek", 7, "2026-08-31", 101.0, 104.0),
        ("TwoWeeks", 14, "2026-09-07", 102.0, 105.0),
        ("OneMonth", 30, "2026-09-23", 103.0, 106.0),
        ("ThreeMonths", 90, "2026-11-22", 104.0, 107.0),
    ]


@pytest.mark.parametrize(
    ("action", "expected_range", "absent_range"),
    [
        ("BUY", "buy_range", "sell_range"),
        ("HOLD", None, None),
        ("SELL", "sell_range", "buy_range"),
    ],
)
def test_sync_ticker_recommendation_exposes_only_the_action_specific_price_range(
    action,
    expected_range,
    absent_range,
):
    async def analysis_with_recommendation(*, symbol, current_holding):
        analysis = await _analysis_for_request(
            symbol=symbol,
            current_holding=current_holding,
        )
        analysis_data = analysis.model_dump(mode="python")
        analysis_data["recommendation"] = ticker_fixtures.make_recommendation(
            action=action,
            holding=False,
        )
        return models_ticker.TickerAnalysis.model_validate(analysis_data)

    with mock.patch(
        "app.routers.ai_ticker.services_ticker.ai_analyze_ticker",
        new=analysis_with_recommendation,
    ):
        response = client.post(
            "/ai/analyze_ticker",
            json=_request_body(include_holding=False),
        )

    assert response.status_code == 200
    recommendation = response.json()["data"]["recommendation"]
    assert recommendation["action"] == action
    if expected_range is None:
        assert "buy_range" not in recommendation
        assert "sell_range" not in recommendation
    else:
        assert recommendation[expected_range]["minimum"] <= recommendation[expected_range]["maximum"]
        assert absent_range not in recommendation


@pytest.mark.parametrize(
    "body",
    [
        {"symbol": "NASDAQ:AAPL", "intent": "buy"},
        {"symbol": "NASDAQ:AAPL", "current_holding": {"num_shares": 0, "avg_price": 100}},
        {"symbol": "NASDAQ:AAPL", "current_holding": {"num_shares": 1, "avg_price": 0}},
        {"symbol": "NASDAQ: AAPL"},
        {"symbol": ""},
    ],
)
def test_ticker_request_schema_rejects_undocumented_or_invalid_inputs(body):
    response = client.post("/ai/analyze_ticker", json=body)

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (services_ticker.TickerInputError("unsupported symbol"), 422),
        (services_ticker.TickerVerificationError("verification unavailable"), 502),
        (services_ticker.TickerAnalysisAIError("analysis unavailable"), 502),
        (ai_helper.LLMRateLimitError("rate-limit budget exhausted"), 502),
    ],
)
def test_sync_ticker_analysis_maps_documented_service_failures(error, expected_status):
    async def fail(**kwargs):
        raise error

    with mock.patch("app.routers.ai_ticker.services_ticker.ai_analyze_ticker", new=fail):
        response = client.post("/ai/analyze_ticker", json=_request_body())

    assert response.status_code == expected_status
    assert response.json()["status"] == expected_status
    assert "data" not in response.json()


def test_async_ticker_lifecycle_returns_running_then_completed_holding_analysis(deferred_task_store):
    with mock.patch(
        "app.routers.ai_ticker.services_ticker.ai_analyze_ticker",
        new=_analysis_for_request,
    ):
        started = client.post("/ai/start_analyze_ticker_async", json=_request_body())
        task_id = started.json()["extra"]["task_id"]
        running = client.post(
            "/ai/poll_analyze_ticker_async",
            params={"task_id": task_id},
        )
        duplicate_running = client.post(
            "/ai/start_analyze_ticker_async",
            json=_request_body(),
        )

        deferred_task_store.release()

        completed = client.post(
            "/ai/poll_analyze_ticker_async",
            params={"task_id": f"  {task_id}  "},
        )
        duplicate_completed = client.post(
            "/ai/start_analyze_ticker_async",
            json=_request_body(),
        )

    assert started.status_code == 202
    assert started.json()["extra"]["state"] == "RUNNING"
    assert running.status_code == 202
    assert duplicate_running.json()["extra"] == {"task_id": task_id, "state": "RUNNING"}
    assert completed.status_code == 200
    assert completed.json()["extra"] == {"task_id": task_id, "state": "COMPLETED"}
    assert completed.json()["data"]["holding_snapshot"]["market_value"] == 1000.0
    assert duplicate_completed.json() == completed.json()


def test_async_ticker_start_distinguishes_missing_and_invalid_bodies():
    missing = client.post("/ai/start_analyze_ticker_async")
    invalid = client.post("/ai/start_analyze_ticker_async", json={"symbol": ""})

    assert missing.status_code == 400
    assert missing.json()["status"] == 400
    assert invalid.status_code == 422
    assert isinstance(invalid.json()["detail"], list)


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (services_ticker.TickerInputError("unsupported symbol"), 422),
        (services_ticker.TickerVerificationError("verification unavailable"), 502),
        (services_ticker.TickerAnalysisAIError("analysis unavailable"), 502),
        (ai_helper.LLMRateLimitError("rate-limit budget exhausted"), 502),
        (RuntimeError("unexpected failure"), 500),
    ],
)
def test_async_ticker_failures_are_pollable_and_deduplicated(
    deferred_task_store,
    error,
    expected_status,
):
    async def fail(**kwargs):
        raise error

    with mock.patch("app.routers.ai_ticker.services_ticker.ai_analyze_ticker", new=fail):
        started = client.post("/ai/start_analyze_ticker_async", json=_request_body())
        task_id = started.json()["extra"]["task_id"]
        deferred_task_store.release()
        failed = client.post(
            "/ai/poll_analyze_ticker_async",
            params={"task_id": task_id},
        )
        duplicate = client.post("/ai/start_analyze_ticker_async", json=_request_body())

    assert started.status_code == 202
    assert failed.status_code == expected_status
    assert failed.json()["extra"] == {"task_id": task_id, "state": "FAILED"}
    assert "data" not in failed.json()
    assert duplicate.status_code == expected_status
    assert duplicate.json()["extra"] == {"task_id": task_id, "state": "FAILED"}
