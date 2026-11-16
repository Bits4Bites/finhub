import asyncio
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app
from app.models import events_dividends as models_dividends
from app.routers import ai_dividend
from app.routers import async_task as router_async_task
from app.schemas import ai_dividend as schemas_dividends
from app.schemas import async_task
from app.services import ai_helper
from app.services import msai_analyze_div_event as service
from tests import dividend_fixtures

client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_task_cache():
    asyncio.run(router_async_task.cache.clear())
    yield
    asyncio.run(router_async_task.cache.clear())


def _request_body() -> dict[str, object]:
    return {
        "symbol": "asx:cba",
        "ex_date": dividend_fixtures.EX_DATE.isoformat(),
        "dividend_amount": 2.0,
    }


def _request_model() -> schemas_dividends.AnalyzeDividendEventRequest:
    return schemas_dividends.AnalyzeDividendEventRequest.model_validate(_request_body())


def _response_for_state(state: async_task.TaskState) -> schemas_dividends.AnalyzeDividendEventResponse:
    if state == async_task.TASK_STATE_FAILED:
        return schemas_dividends.AnalyzeDividendEventResponse(
            status=502,
            message="Dividend research failed",
            data=dividend_fixtures.failed_analysis(),
        )
    return schemas_dividends.AnalyzeDividendEventResponse(
        status=200,
        message="ok",
        data=dividend_fixtures.complete_analysis(),
    )


async def _seed_task(state: async_task.TaskState) -> str:
    task_id, _ = await router_async_task.start_task("analyze_dividend_event", _request_model())
    if state == async_task.TASK_STATE_COMPLETED:
        result = _response_for_state(state)
        await router_async_task.complete_task(
            task_id,
            "analyze_dividend_event",
            result,
            status_code=result.status,
            message=result.message,
        )
    elif state == async_task.TASK_STATE_FAILED:
        result = _response_for_state(state)
        await router_async_task.fail_task(
            task_id,
            "analyze_dividend_event",
            status_code=result.status,
            message=result.message,
            result=result,
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
            "/ai/analyze_dividend_event",
            json=_request_body(),
            follow_redirects=False,
        )

    assert response.status_code == 307
    assert response.headers["location"] == "https://proxy.example/finhub/ai/analyze_dividend_event"


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
            "/ai/start_analyze_dividend_event_async",
            json=_request_body(),
            follow_redirects=False,
        )

    assert response.status_code == 307
    assert response.headers["location"] == "https://proxy.example/finhub/ai/start_analyze_dividend_event_async"


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
            "/ai/poll_analyze_dividend_event_async",
            params={"task_id": "task-123"},
            follow_redirects=False,
        )

    assert response.status_code == 307
    assert (
        response.headers["location"]
        == "https://proxy.example/finhub/ai/poll_analyze_dividend_event_async?task_id=task-123"
    )


def test_request_schema_has_class_and_field_documentation():
    schema = schemas_dividends.AnalyzeDividendEventRequest.model_json_schema()

    assert schema["description"].startswith("Request to research and assess a dividend event.")
    assert all(
        schema["properties"][field_name]["description"]
        for field_name in (
            "symbol",
            "ex_date",
            "dividend_amount",
            "transaction_costs",
            "holding_period_days",
        )
    )


def test_openapi_requires_async_start_body_and_documents_public_outcomes():
    paths = client.get("/openapi.json").json()["paths"]
    sync_responses = paths["/ai/analyze_dividend_event"]["post"]["responses"]
    start_operation = paths["/ai/start_analyze_dividend_event_async"]["post"]
    poll_responses = paths["/ai/poll_analyze_dividend_event_async"]["post"]["responses"]

    assert start_operation["requestBody"]["required"] is True
    assert {"200", "400", "422", "500", "502"} <= set(sync_responses)
    assert {"200", "202", "400", "404", "422", "500", "502"} <= set(start_operation["responses"])
    assert {"200", "202", "400", "404", "422", "500", "502"} <= set(poll_responses)


def test_post_analyzes_typed_request():
    analysis = dividend_fixtures.complete_analysis()
    with mock.patch.object(
        ai_dividend.services_dividend,
        "ai_analyze_div_event",
        new_callable=mock.AsyncMock,
        return_value=analysis,
    ) as mock_analyze:
        response = client.post("/ai/analyze_dividend_event", json=_request_body())

    assert response.status_code == 200
    assert response.json()["data"]["analysis_status"] == "Complete"
    assert mock_analyze.await_args.kwargs["symbol"] == "ASX:CBA"
    assert mock_analyze.await_args.kwargs["ex_date"] == dividend_fixtures.EX_DATE


def test_post_rejects_invalid_dividend_amount():
    body = _request_body()
    body["dividend_amount"] = 0

    response = client.post("/ai/analyze_dividend_event", json=body)

    assert response.status_code == 422


def test_post_rejects_removed_intent_field():
    body = _request_body()
    body["intent"] = "Prefer dividend capture"

    response = client.post("/ai/analyze_dividend_event", json=body)

    assert response.status_code == 422


def test_post_maps_input_error_to_400():
    with mock.patch.object(
        ai_dividend.services_dividend,
        "ai_analyze_div_event",
        new_callable=mock.AsyncMock,
        side_effect=service.DividendEventInputError("Unsupported or unknown asset type"),
    ):
        response = client.post("/ai/analyze_dividend_event", json=_request_body())

    assert response.status_code == 400
    assert response.json()["status"] == 400
    assert response.json()["message"]


def test_post_maps_insufficient_data_to_422():
    with mock.patch.object(
        ai_dividend.services_dividend,
        "ai_analyze_div_event",
        new_callable=mock.AsyncMock,
        side_effect=service.DividendEventInsufficientDataError("Insufficient market history"),
    ):
        response = client.post("/ai/analyze_dividend_event", json=_request_body())

    assert response.status_code == 422
    assert response.json()["status"] == 422
    assert response.json()["message"]


@pytest.mark.parametrize(
    "error",
    [
        service.DividendEventAIError("Provider output failed"),
        ai_helper.LLMRateLimitError("Provider remained rate limited"),
    ],
)
def test_post_maps_raised_ai_failures_to_502(error):
    with mock.patch.object(
        ai_dividend.services_dividend,
        "ai_analyze_div_event",
        new_callable=mock.AsyncMock,
        side_effect=error,
    ):
        response = client.post("/ai/analyze_dividend_event", json=_request_body())

    assert response.status_code == 502
    assert response.json()["status"] == 502
    assert response.json()["message"]


def test_post_preserves_baseline_on_ai_failure():
    with mock.patch.object(
        ai_dividend.services_dividend,
        "ai_analyze_div_event",
        new_callable=mock.AsyncMock,
        return_value=dividend_fixtures.failed_analysis(),
    ):
        response = client.post("/ai/analyze_dividend_event", json=_request_body())

    assert response.status_code == 502
    assert response.json()["data"]["analysis_status"] == "Failed"
    assert response.json()["data"]["historical_baseline"]["sample_count"] == 5


def test_post_returns_completed_analysis_with_validation_warnings():
    analysis_data = dividend_fixtures.complete_analysis().model_dump()
    analysis_data["analysis_status"] = "CompleteWithWarnings"
    analysis_data["validation_warnings"] = ["DividendCapture profit-and-loss estimates were corrected."]
    analysis = models_dividends.DividendEventAnalysis.model_validate(analysis_data)
    with mock.patch.object(
        ai_dividend.services_dividend,
        "ai_analyze_div_event",
        new_callable=mock.AsyncMock,
        return_value=analysis,
    ):
        response = client.post("/ai/analyze_dividend_event", json=_request_body())

    assert response.status_code == 200
    assert response.json()["data"]["analysis_status"] == "CompleteWithWarnings"
    assert response.json()["data"]["validation_warnings"] == analysis_data["validation_warnings"]


def test_async_start_to_poll_returns_service_analysis():
    with mock.patch.object(
        ai_dividend.services_dividend,
        "ai_analyze_div_event",
        new_callable=mock.AsyncMock,
        return_value=dividend_fixtures.complete_analysis(),
    ) as mock_analyze:
        start_response = client.post(
            "/ai/start_analyze_dividend_event_async",
            json=_request_body(),
        )

    task_id = start_response.json()["extra"]["task_id"]
    poll_response = client.post(
        "/ai/poll_analyze_dividend_event_async",
        params={"task_id": task_id},
    )

    assert start_response.status_code == 202
    assert start_response.json()["extra"]["state"] == async_task.TASK_STATE_RUNNING
    assert poll_response.status_code == 200
    assert poll_response.json()["extra"] == {
        "task_id": task_id,
        "state": async_task.TASK_STATE_COMPLETED,
    }
    assert poll_response.json()["data"]["analysis_status"] == "Complete"
    assert mock_analyze.await_args.kwargs["symbol"] == "ASX:CBA"
    assert mock_analyze.await_args.kwargs["ex_date"] == dividend_fixtures.EX_DATE


def test_async_start_requires_request_body():
    response = client.post("/ai/start_analyze_dividend_event_async")

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

    response = client.post("/ai/start_analyze_dividend_event_async", json=_request_body())

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
def test_poll_returns_running_completed_and_failed_tasks(task_state, expected_status):
    task_id = asyncio.run(_seed_task(task_state))

    response = client.post(
        "/ai/poll_analyze_dividend_event_async",
        params={"task_id": f"  {task_id}  "},
    )

    assert response.status_code == expected_status
    assert response.json()["extra"] == {"task_id": task_id, "state": task_state}
    if task_state == async_task.TASK_STATE_COMPLETED:
        assert response.json()["data"]["analysis_status"] == "Complete"
    elif task_state == async_task.TASK_STATE_FAILED:
        assert response.json()["data"]["historical_baseline"]["sample_count"] == 5
    else:
        assert "data" not in response.json()


def test_poll_returns_404_for_missing_task():
    response = client.post(
        "/ai/poll_analyze_dividend_event_async",
        params={"task_id": "missing-task"},
    )

    assert response.status_code == 404
    assert response.json()["status"] == 404


def test_poll_returns_500_for_invalid_task_state():
    with mock.patch.object(
        router_async_task.cache,
        "get",
        new_callable=mock.AsyncMock,
        return_value={"task_type": "analyze_dividend_event", "state": "UNKNOWN"},
    ):
        response = client.post(
            "/ai/poll_analyze_dividend_event_async",
            params={"task_id": "invalid-task"},
        )

    assert response.status_code == 500
    assert response.json()["status"] == 500


def test_async_provider_rate_limit_is_exposed_as_502_when_polled():
    with mock.patch.object(
        ai_dividend.services_dividend,
        "ai_analyze_div_event",
        new_callable=mock.AsyncMock,
        side_effect=ai_helper.LLMRateLimitError("Provider remained rate limited"),
    ):
        start_response = client.post(
            "/ai/start_analyze_dividend_event_async",
            json=_request_body(),
        )

    poll_response = client.post(
        "/ai/poll_analyze_dividend_event_async",
        params={"task_id": start_response.json()["extra"]["task_id"]},
    )

    assert start_response.status_code == 202
    assert poll_response.status_code == 502
    assert poll_response.json()["status"] == 502
    assert poll_response.json()["extra"]["state"] == async_task.TASK_STATE_FAILED
