"""Tests for the dedicated ticker-analysis API routes."""

import asyncio
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app
from app.routers import ai_ticker as router_ticker
from app.routers import async_task as router_async_task
from app.schemas import ai_ticker as schemas_ticker
from app.schemas import async_task
from app.services import ai_helper
from app.services import msai_analyze_ticker as services_ticker
from tests import ticker_fixtures

client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_task_cache():
    asyncio.run(router_async_task.cache.clear())
    yield
    asyncio.run(router_async_task.cache.clear())


def _request_body() -> dict[str, str]:
    return {"symbol": "nasdaq:aapl"}


def _request_model() -> schemas_ticker.AnalyzeTickerRequest:
    return schemas_ticker.AnalyzeTickerRequest.model_validate(_request_body())


async def _seed_task(state: async_task.TaskState) -> str:
    task_id, _ = await router_async_task.start_task("analyze_ticker", _request_model())
    if state == async_task.TASK_STATE_COMPLETED:
        result = schemas_ticker.AnalyzeTickerResponse(
            status=200,
            message="ok",
            data=ticker_fixtures.make_analysis(),
        )
        await router_async_task.complete_task(
            task_id,
            "analyze_ticker",
            result,
            status_code=result.status,
            message=result.message,
        )
    elif state == async_task.TASK_STATE_FAILED:
        await router_async_task.fail_task(
            task_id,
            "analyze_ticker",
            status_code=502,
            message="Ticker research failed",
        )
    return task_id


def test_sync_redirects_through_ai_proxy_handler():
    with (
        mock.patch.object(config.settings_finhub_proxy, "proxy_mode", "Redirect"),
        mock.patch.object(
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


def test_async_start_redirects_through_ai_proxy_handler():
    with (
        mock.patch.object(config.settings_finhub_proxy, "proxy_mode", "Redirect"),
        mock.patch.object(
            config.settings_finhub_proxy,
            "url_ai_task_node",
            "https://proxy.example/finhub/",
        ),
    ):
        response = client.post(
            "/ai/start_analyze_ticker_async",
            json=_request_body(),
            follow_redirects=False,
        )

    assert response.status_code == 307
    assert response.headers["location"] == "https://proxy.example/finhub/ai/start_analyze_ticker_async"


def test_openapi_requires_async_start_body_and_documents_public_outcomes():
    paths = client.get("/openapi.json").json()["paths"]
    sync_responses = paths["/ai/analyze_ticker"]["post"]["responses"]
    start_operation = paths["/ai/start_analyze_ticker_async"]["post"]
    poll_responses = paths["/ai/poll_analyze_ticker_async"]["post"]["responses"]

    assert start_operation["requestBody"]["required"] is True
    assert {"200", "422", "500", "502"} <= set(sync_responses)
    assert {"200", "202", "400", "404", "422", "500", "502"} <= set(start_operation["responses"])
    assert {"200", "202", "404", "422", "500", "502"} <= set(poll_responses)


def test_sync_returns_structured_analysis_and_passes_holding():
    analysis = ticker_fixtures.make_analysis()
    with mock.patch.object(
        router_ticker.services_ticker,
        "ai_analyze_ticker",
        new_callable=mock.AsyncMock,
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


def test_sync_succeeds_without_optional_holding():
    with mock.patch.object(
        router_ticker.services_ticker,
        "ai_analyze_ticker",
        new_callable=mock.AsyncMock,
        return_value=ticker_fixtures.make_analysis(),
    ) as analyze:
        response = client.post("/ai/analyze_ticker", json=_request_body())

    assert response.status_code == 200
    assert response.json()["data"]["symbol"] == "NASDAQ:AAPL"
    assert analyze.await_args.kwargs["current_holding"] is None


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
    with mock.patch.object(
        router_ticker.services_ticker,
        "ai_analyze_ticker",
        new_callable=mock.AsyncMock,
        side_effect=services_ticker.TickerInputError("Unsupported security type"),
    ):
        response = client.post("/ai/analyze_ticker", json={"symbol": "FX:USD"})

    assert response.status_code == 422
    assert response.json()["status"] == 422
    assert response.json()["message"]


@pytest.mark.parametrize(
    "error",
    [
        services_ticker.TickerVerificationError("Market data unavailable"),
        services_ticker.TickerAnalysisAIError("AI output invalid"),
    ],
)
def test_sync_maps_verification_and_explicit_ai_errors_to_502(error):
    with mock.patch.object(
        router_ticker.services_ticker,
        "ai_analyze_ticker",
        new_callable=mock.AsyncMock,
        side_effect=error,
    ):
        response = client.post("/ai/analyze_ticker", json={"symbol": "NASDAQ:AAPL"})

    assert response.status_code == 502
    assert response.json()["status"] == 502
    assert response.json()["message"]


def test_sync_maps_rate_limit_to_502():
    with mock.patch.object(
        router_ticker.services_ticker,
        "ai_analyze_ticker",
        new_callable=mock.AsyncMock,
        side_effect=ai_helper.LLMRateLimitError("Provider remained rate limited"),
    ):
        response = client.post("/ai/analyze_ticker", json=_request_body())

    assert response.status_code == 502
    assert response.json()["status"] == 502
    assert response.json()["message"]


def test_request_rejects_invalid_holding():
    response = client.post(
        "/ai/analyze_ticker",
        json={
            "symbol": "NASDAQ:AAPL",
            "current_holding": {"num_shares": 0, "avg_price": 80},
        },
    )

    assert response.status_code == 422


def test_async_start_to_poll_returns_service_analysis():
    with mock.patch.object(
        router_ticker.services_ticker,
        "ai_analyze_ticker",
        new_callable=mock.AsyncMock,
        return_value=ticker_fixtures.make_analysis(),
    ) as analyze:
        start_response = client.post(
            "/ai/start_analyze_ticker_async",
            json=_request_body(),
        )

    task_id = start_response.json()["extra"]["task_id"]
    poll_response = client.post(
        "/ai/poll_analyze_ticker_async",
        params={"task_id": task_id},
    )

    assert start_response.status_code == 202
    assert start_response.json()["extra"]["state"] == async_task.TASK_STATE_RUNNING
    assert poll_response.status_code == 200
    assert poll_response.json()["extra"] == {
        "task_id": task_id,
        "state": async_task.TASK_STATE_COMPLETED,
    }
    assert poll_response.json()["data"]["symbol"] == "NASDAQ:AAPL"
    assert analyze.await_args.kwargs["symbol"] == "NASDAQ:AAPL"
    assert analyze.await_args.kwargs["current_holding"] is None


def test_async_poll_redirects_through_ai_proxy_handler():
    with (
        mock.patch.object(config.settings_finhub_proxy, "proxy_mode", "Redirect"),
        mock.patch.object(
            config.settings_finhub_proxy,
            "url_ai_task_node",
            "https://proxy.example/finhub/",
        ),
    ):
        response = client.post(
            "/ai/poll_analyze_ticker_async",
            params={"task_id": "task-456"},
            follow_redirects=False,
        )

    assert response.status_code == 307
    assert response.headers["location"] == "https://proxy.example/finhub/ai/poll_analyze_ticker_async?task_id=task-456"


def test_async_requires_body_when_starting():
    response = client.post("/ai/start_analyze_ticker_async")

    assert response.status_code == 400
    assert response.json() == {
        "status": 400,
        "message": "Request body is required when starting a task",
    }


@pytest.mark.parametrize(
    ("task_state", "expected_status"),
    [
        (async_task.TASK_STATE_RUNNING, 202),
        (async_task.TASK_STATE_COMPLETED, 200),
        (async_task.TASK_STATE_FAILED, 502),
    ],
)
def test_async_start_deduplicates_running_completed_and_failed_tasks(task_state, expected_status):
    task_id = asyncio.run(_seed_task(task_state))

    response = client.post("/ai/start_analyze_ticker_async", json=_request_body())

    assert response.status_code == expected_status
    assert response.json()["extra"] == {"task_id": task_id, "state": task_state}


@pytest.mark.parametrize(
    ("task_state", "expected_status"),
    [
        (async_task.TASK_STATE_RUNNING, 202),
        (async_task.TASK_STATE_COMPLETED, 200),
        (async_task.TASK_STATE_FAILED, 502),
    ],
)
def test_async_poll_returns_running_completed_and_failed_tasks(task_state, expected_status):
    task_id = asyncio.run(_seed_task(task_state))

    response = client.post(
        "/ai/poll_analyze_ticker_async",
        params={"task_id": f"  {task_id}  "},
    )

    assert response.status_code == expected_status
    assert response.json()["extra"] == {"task_id": task_id, "state": task_state}
    if task_state == async_task.TASK_STATE_COMPLETED:
        assert response.json()["data"]["forecasts"][3]["horizon"] == "ThreeMonths"
    else:
        assert "data" not in response.json()


def test_async_poll_returns_404_for_missing_task():
    response = client.post(
        "/ai/poll_analyze_ticker_async",
        params={"task_id": "missing-task"},
    )

    assert response.status_code == 404
    assert response.json()["status"] == 404


def test_async_poll_returns_500_for_invalid_task_state():
    with mock.patch.object(
        router_async_task.cache,
        "get",
        new_callable=mock.AsyncMock,
        return_value={"task_type": "analyze_ticker", "state": "UNKNOWN"},
    ):
        response = client.post(
            "/ai/poll_analyze_ticker_async",
            params={"task_id": "invalid-task"},
        )

    assert response.status_code == 500
    assert response.json()["status"] == 500


def test_async_explicit_ai_error_is_exposed_as_502_when_polled():
    with mock.patch.object(
        router_ticker.services_ticker,
        "ai_analyze_ticker",
        new_callable=mock.AsyncMock,
        side_effect=services_ticker.TickerAnalysisAIError("AI output invalid"),
    ):
        start_response = client.post(
            "/ai/start_analyze_ticker_async",
            json=_request_body(),
        )

    poll_response = client.post(
        "/ai/poll_analyze_ticker_async",
        params={"task_id": start_response.json()["extra"]["task_id"]},
    )

    assert start_response.status_code == 202
    assert poll_response.status_code == 502
    assert poll_response.json()["status"] == 502
    assert poll_response.json()["extra"]["state"] == async_task.TASK_STATE_FAILED


def test_async_rate_limit_persists_502_and_duplicate_start_reuses_failure():
    with mock.patch.object(
        router_ticker.services_ticker,
        "ai_analyze_ticker",
        new_callable=mock.AsyncMock,
        side_effect=ai_helper.LLMRateLimitError("Provider remained rate limited"),
    ) as analyze:
        start_response = client.post(
            "/ai/start_analyze_ticker_async",
            json=_request_body(),
        )

        task_id = start_response.json()["extra"]["task_id"]
        poll_response = client.post(
            "/ai/poll_analyze_ticker_async",
            params={"task_id": task_id},
        )
        duplicate_response = client.post(
            "/ai/start_analyze_ticker_async",
            json=_request_body(),
        )

    assert start_response.status_code == 202
    assert poll_response.status_code == 502
    assert poll_response.json()["extra"] == {
        "task_id": task_id,
        "state": async_task.TASK_STATE_FAILED,
    }
    assert duplicate_response.status_code == 502
    assert duplicate_response.json()["extra"] == {
        "task_id": task_id,
        "state": async_task.TASK_STATE_FAILED,
    }
    analyze.assert_awaited_once()
