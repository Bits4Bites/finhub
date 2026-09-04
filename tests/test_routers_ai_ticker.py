"""Tests for the dedicated ticker-analysis API routes."""

import asyncio
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app import config
from app.main import app
from app.routers import ai_ticker as router_ticker
from app.schemas import ai_ticker as schemas_ticker
from app.schemas import async_task
from app.services import msai_analyze_ticker as services_ticker
from tests import ticker_fixtures

client = TestClient(app)


def test_sync_redirects_through_ai_proxy_handler():
    with (
        patch.object(config.settings_finhub_proxy, "proxy_mode", "Redirect"),
        patch.object(
            config.settings_finhub_proxy,
            "url_ai_task_node",
            "https://proxy.example/finhub/",
        ),
    ):
        response = client.post(
            "/ai/analyze_ticker",
            json={"symbol": "NASDAQ:AAPL"},
            follow_redirects=False,
        )

    assert response.status_code == 307
    assert response.headers["location"] == "https://proxy.example/finhub/ai/analyze_ticker"


def test_sync_returns_structured_analysis_and_passes_holding():
    analysis = ticker_fixtures.make_analysis()
    with patch(
        "app.routers.ai_ticker.services_ticker.ai_analyze_ticker",
        new_callable=AsyncMock,
        return_value=analysis,
    ) as analyze:
        response = client.post(
            "/ai/analyze_ticker",
            json={
                "symbol": "nasdaq:aapl",
                "current_holding": {"num_shares": 10, "avg_price": 80},
            },
        )

    assert response.status_code == 200
    assert response.json()["data"]["symbol"] == "NASDAQ:AAPL"
    request = analyze.await_args.kwargs
    assert request["symbol"] == "NASDAQ:AAPL"
    assert request["current_holding"].num_shares == 10


def test_request_rejects_removed_intent():
    response = client.post(
        "/ai/analyze_ticker",
        json={
            "symbol": "NASDAQ:AAPL",
            "intent": "Focus on margins",
        },
    )

    assert response.status_code == 422


def test_sync_maps_input_error_to_422():
    with patch(
        "app.routers.ai_ticker.services_ticker.ai_analyze_ticker",
        new_callable=AsyncMock,
        side_effect=services_ticker.TickerInputError("Unsupported security type"),
    ):
        response = client.post("/ai/analyze_ticker", json={"symbol": "FX:USD"})

    assert response.status_code == 422
    assert response.json() == {"status": 422, "message": "Unsupported security type"}


def test_sync_maps_provider_error_to_502():
    with patch(
        "app.routers.ai_ticker.services_ticker.ai_analyze_ticker",
        new_callable=AsyncMock,
        side_effect=services_ticker.TickerVerificationError("Market data unavailable"),
    ):
        response = client.post("/ai/analyze_ticker", json={"symbol": "NASDAQ:AAPL"})

    assert response.status_code == 502
    assert response.json() == {"status": 502, "message": "Market data unavailable"}


def test_request_rejects_invalid_holding():
    response = client.post(
        "/ai/analyze_ticker",
        json={
            "symbol": "NASDAQ:AAPL",
            "current_holding": {"num_shares": 0, "avg_price": 80},
        },
    )

    assert response.status_code == 422


def test_async_starts_with_normalized_request():
    with (
        patch("app.routers.async_task._generate_task_id", return_value="task-456"),
        patch("app.routers.async_task.cache.set", new_callable=AsyncMock, return_value=True),
        patch("app.routers.ai_ticker._run_task", new_callable=AsyncMock) as run_task,
    ):
        response = client.post(
            "/ai/analyze_ticker_async",
            json={"symbol": "nasdaq:aapl"},
        )

    assert response.status_code == 202
    assert response.json()["extra"] == {
        "task_id": "task-456",
        "state": async_task.TASK_STATE_RUNNING,
    }
    task_request = run_task.await_args.args[1]
    assert task_request.symbol == "NASDAQ:AAPL"


def test_async_poll_redirects_through_ai_proxy_handler():
    with (
        patch.object(config.settings_finhub_proxy, "proxy_mode", "Redirect"),
        patch.object(
            config.settings_finhub_proxy,
            "url_ai_task_node",
            "https://proxy.example/finhub/",
        ),
    ):
        response = client.post(
            "/ai/analyze_ticker_async",
            params={"task_id": "task-456"},
            follow_redirects=False,
        )

    assert response.status_code == 307
    assert response.headers["location"] == "https://proxy.example/finhub/ai/analyze_ticker_async?task_id=task-456"


def test_async_requires_body_when_starting():
    response = client.post("/ai/analyze_ticker_async")

    assert response.status_code == 400
    assert response.json() == {
        "status": 400,
        "message": "Request body is required when starting a task",
    }


def test_async_poll_preserves_502_failure_status():
    task_entry = {
        "task_type": "analyze_ticker",
        "state": async_task.TASK_STATE_FAILED,
        "status": 502,
        "message": "Ticker research failed",
    }
    with patch(
        "app.routers.async_task.cache.get",
        new_callable=AsyncMock,
        return_value=task_entry,
    ):
        response = client.post("/ai/analyze_ticker_async", params={"task_id": "task-456"})

    assert response.status_code == 502
    assert response.json()["status"] == 502
    assert response.json()["message"] == "Ticker research failed"


def test_async_poll_returns_structured_completed_result():
    result = schemas_ticker.AnalyzeTickerResponse(
        status=200,
        message="ok",
        data=ticker_fixtures.make_analysis(),
    )
    task_entry = {
        "task_type": "analyze_ticker",
        "state": async_task.TASK_STATE_COMPLETED,
        "status": 200,
        "message": "ok",
        "result": result.model_dump(mode="json"),
    }
    with patch(
        "app.routers.async_task.cache.get",
        new_callable=AsyncMock,
        return_value=task_entry,
    ):
        response = client.post("/ai/analyze_ticker_async", params={"task_id": "task-456"})

    assert response.status_code == 200
    assert response.json()["data"]["forecasts"][3]["horizon"] == "ThreeMonths"


def test_background_task_preserves_http_failure():
    request = schemas_ticker.AnalyzeTickerRequest(symbol="NASDAQ:AAPL")
    with (
        patch(
            "app.routers.ai_ticker._analyze",
            new_callable=AsyncMock,
            side_effect=services_ticker.TickerAnalysisAIError("invalid output"),
        ),
        patch("app.routers.async_task.cache.set", new_callable=AsyncMock) as cache_set,
    ):
        asyncio.run(router_ticker._run_task("task-456", request))

    stored = cache_set.await_args.args[1]
    assert stored["state"] == async_task.TASK_STATE_FAILED
    assert stored["status"] == 500


def test_background_task_preserves_mapped_failure():
    from fastapi import HTTPException

    request = schemas_ticker.AnalyzeTickerRequest(symbol="NASDAQ:AAPL")
    with (
        patch(
            "app.routers.ai_ticker._analyze",
            new_callable=AsyncMock,
            side_effect=HTTPException(status_code=502, detail="invalid output"),
        ),
        patch("app.routers.async_task.cache.set", new_callable=AsyncMock) as cache_set,
    ):
        asyncio.run(router_ticker._run_task("task-456", request))

    stored = cache_set.await_args.args[1]
    assert stored["state"] == async_task.TASK_STATE_FAILED
    assert stored["status"] == 502
    assert stored["message"] == "invalid output"
