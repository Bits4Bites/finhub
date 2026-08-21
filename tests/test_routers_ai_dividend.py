import asyncio
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.models import events_dividends as models_dividends
from app.routers import ai_dividend
from app.schemas import ai_dividend as schemas_dividends
from app.schemas import async_task
from app.services import msai_analyze_div_event as service
from tests import dividend_fixtures

client = TestClient(app)


def _request_body() -> dict[str, object]:
    return {
        "symbol": "asx:cba",
        "ex_date": dividend_fixtures.EX_DATE.isoformat(),
        "dividend_amount": 2.0,
    }


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


def test_post_analyzes_typed_request():
    analysis = dividend_fixtures.complete_analysis()
    with patch.object(
        ai_dividend.services_dividend,
        "ai_analyze_div_event",
        new_callable=AsyncMock,
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
    with patch.object(
        ai_dividend.services_dividend,
        "ai_analyze_div_event",
        new_callable=AsyncMock,
        side_effect=service.DividendEventInputError("Unsupported or unknown asset type"),
    ):
        response = client.post("/ai/analyze_dividend_event", json=_request_body())

    assert response.status_code == 400
    assert response.json()["message"] == "Unsupported or unknown asset type"


def test_post_preserves_baseline_on_ai_failure():
    with patch.object(
        ai_dividend.services_dividend,
        "ai_analyze_div_event",
        new_callable=AsyncMock,
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
    with patch.object(
        ai_dividend.services_dividend,
        "ai_analyze_div_event",
        new_callable=AsyncMock,
        return_value=analysis,
    ):
        response = client.post("/ai/analyze_dividend_event", json=_request_body())

    assert response.status_code == 200
    assert response.json()["data"]["analysis_status"] == "CompleteWithWarnings"
    assert response.json()["data"]["validation_warnings"] == analysis_data["validation_warnings"]


def test_async_start_uses_post_body():
    with (
        patch.object(ai_dividend.uuid, "uuid4", return_value="task-123"),
        patch.object(ai_dividend.cache, "set", new_callable=AsyncMock, return_value=True),
        patch.object(ai_dividend, "_run_task", new_callable=AsyncMock) as mock_run,
    ):
        response = client.post("/ai/analyze_dividend_event_async", json=_request_body())

    assert response.status_code == 202
    assert response.json()["extra"] == {
        "task_id": "task-123",
        "state": async_task.TASK_STATE_RUNNING,
    }
    request = mock_run.await_args.args[1]
    assert request.symbol == "asx:cba"


def test_poll_returns_running_task():
    task_entry = {
        "task_type": "analyze_dividend_event",
        "state": async_task.TASK_STATE_RUNNING,
    }
    with patch.object(
        ai_dividend.cache,
        "get",
        new_callable=AsyncMock,
        return_value=task_entry,
    ):
        response = client.get("/ai/analyze_dividend_event_async/task-123")

    assert response.status_code == 202
    assert response.json()["extra"]["state"] == async_task.TASK_STATE_RUNNING


def test_poll_returns_completed_result():
    result = schemas_dividends.AnalyzeDividendEventResponse(
        status=200,
        message="ok",
        data=dividend_fixtures.complete_analysis(),
    )
    task_entry = {
        "task_type": "analyze_dividend_event",
        "state": async_task.TASK_STATE_COMPLETED,
        "result": result.model_dump(mode="json"),
    }
    with patch.object(
        ai_dividend.cache,
        "get",
        new_callable=AsyncMock,
        return_value=task_entry,
    ):
        response = client.get("/ai/analyze_dividend_event_async/task-123")

    assert response.status_code == 200
    assert response.json()["data"]["recommendation"]["outcome"] == "DividendCapture"


def test_poll_returns_failed_result_with_baseline():
    result = schemas_dividends.AnalyzeDividendEventResponse(
        status=502,
        message="Dividend research failed",
        data=dividend_fixtures.failed_analysis(),
    )
    task_entry = {
        "task_type": "analyze_dividend_event",
        "state": async_task.TASK_STATE_FAILED,
        "status": 502,
        "message": result.message,
        "result": result.model_dump(mode="json"),
    }
    with patch.object(
        ai_dividend.cache,
        "get",
        new_callable=AsyncMock,
        return_value=task_entry,
    ):
        response = client.get("/ai/analyze_dividend_event_async/task-123")

    assert response.status_code == 502
    assert response.json()["data"]["historical_baseline"]["sample_count"] == 5


def test_background_task_caches_failure_result():
    response = schemas_dividends.AnalyzeDividendEventResponse(
        status=502,
        message="Dividend research failed",
        data=dividend_fixtures.failed_analysis(),
    )
    request = schemas_dividends.AnalyzeDividendEventRequest.model_validate(_request_body())
    with (
        patch.object(ai_dividend, "_analyze", new_callable=AsyncMock, return_value=response),
        patch.object(ai_dividend.cache, "set", new_callable=AsyncMock, return_value=True) as mock_set,
    ):
        asyncio.run(ai_dividend._run_task("task-123", request))

    cached_entry = mock_set.await_args.args[1]
    assert cached_entry["state"] == async_task.TASK_STATE_FAILED
    assert cached_entry["status"] == 502
    assert cached_entry["result"]["data"]["analysis_status"] == "Failed"
