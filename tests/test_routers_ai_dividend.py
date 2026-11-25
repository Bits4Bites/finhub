from unittest import mock

import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app
from app.models import events_div as models_dividends
from app.services import ai_helper
from app.services import msai_analyze_div_event as services_dividend
from tests import dividend_fixtures

client = TestClient(app)


@pytest.fixture(autouse=True)
def disable_ai_proxy(monkeypatch):
    monkeypatch.setattr(config.settings_finhub_proxy, "proxy_mode", "None")
    monkeypatch.setattr(config.settings_finhub_proxy, "url_ai_task_node", "")


def _request_body(**overrides) -> dict[str, object]:
    body: dict[str, object] = {
        "symbol": "asx:cba",
        "ex_date": dividend_fixtures.EX_DATE.isoformat(),
        "dividend_amount": 2.5,
    }
    body.update(overrides)
    return body


async def _analysis_for_request(
    *,
    symbol,
    ex_date,
    dividend_amount,
    transaction_costs,
    holding_period_days,
) -> models_dividends.DividendEventAnalysis:
    analysis = dividend_fixtures.complete_analysis()
    event_data = analysis.event.model_dump()
    event_data.update(
        {
            "symbol": symbol,
            "ex_date": ex_date,
            "dividend_amount": dividend_amount,
            "gross_dividend_yield": dividend_amount / event_data["reference_price"],
            "transaction_costs": transaction_costs,
            "holding_period_days": holding_period_days,
        }
    )
    event = models_dividends.DividendEventContext.model_validate(event_data)
    analysis_data = analysis.model_dump(mode="python")
    analysis_data["event"] = event
    return models_dividends.DividendEventAnalysis.model_validate(analysis_data)


def test_sync_dividend_analysis_exposes_normalized_inputs_and_documented_defaults():
    with mock.patch(
        "app.routers.ai_dividend.services_dividend.ai_analyze_div_event",
        new=_analysis_for_request,
    ):
        response = client.post("/ai/analyze_dividend_event", json=_request_body())

    assert response.status_code == 200
    event = response.json()["data"]["event"]
    assert event["symbol"] == "ASX:CBA"
    assert event["ex_date"] == dividend_fixtures.EX_DATE.isoformat()
    assert event["dividend_amount"] == 2.5
    assert event["holding_period_days"] == 28
    assert event["transaction_costs"] == {
        "dividend_capture_per_share": 0.0,
        "post_dividend_discount_per_share": 0.0,
    }


def test_sync_dividend_analysis_exposes_supplied_costs_and_holding_window():
    with mock.patch(
        "app.routers.ai_dividend.services_dividend.ai_analyze_div_event",
        new=_analysis_for_request,
    ):
        response = client.post(
            "/ai/analyze_dividend_event",
            json=_request_body(
                transaction_costs={
                    "dividend_capture_per_share": 0.12,
                    "post_dividend_discount_per_share": 0.34,
                },
                holding_period_days=45,
            ),
        )

    assert response.status_code == 200
    event = response.json()["data"]["event"]
    assert event["holding_period_days"] == 45
    assert event["transaction_costs"]["dividend_capture_per_share"] == 0.12
    assert event["transaction_costs"]["post_dividend_discount_per_share"] == 0.34


@pytest.mark.parametrize("holding_period_days", [1, 365])
def test_dividend_analysis_accepts_documented_holding_window_boundaries(holding_period_days):
    with mock.patch(
        "app.routers.ai_dividend.services_dividend.ai_analyze_div_event",
        new=_analysis_for_request,
    ):
        response = client.post(
            "/ai/analyze_dividend_event",
            json=_request_body(holding_period_days=holding_period_days),
        )

    assert response.status_code == 200
    assert response.json()["data"]["event"]["holding_period_days"] == holding_period_days


@pytest.mark.parametrize(
    "body",
    [
        _request_body(dividend_amount=0),
        _request_body(holding_period_days=0),
        _request_body(holding_period_days=366),
        _request_body(ex_date="2026-2-1"),
        _request_body(intent="capture"),
    ],
)
def test_dividend_request_schema_rejects_invalid_or_removed_inputs(body):
    response = client.post("/ai/analyze_dividend_event", json=body)

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (services_dividend.DividendEventInputError("invalid event"), 400),
        (services_dividend.DividendEventInsufficientDataError("insufficient history"), 422),
        (services_dividend.DividendEventAIError("analysis unavailable"), 502),
        (ai_helper.LLMRateLimitError("rate-limit budget exhausted"), 502),
    ],
)
def test_sync_dividend_analysis_maps_documented_service_failures(error, expected_status):
    async def fail(**kwargs):
        raise error

    with mock.patch(
        "app.routers.ai_dividend.services_dividend.ai_analyze_div_event",
        new=fail,
    ):
        response = client.post("/ai/analyze_dividend_event", json=_request_body())

    assert response.status_code == expected_status
    assert response.json()["status"] == expected_status
    assert "data" not in response.json()


def test_sync_dividend_analysis_preserves_deterministic_baseline_when_ai_result_failed():
    async def failed_analysis(**kwargs):
        return dividend_fixtures.failed_analysis()

    with mock.patch(
        "app.routers.ai_dividend.services_dividend.ai_analyze_div_event",
        new=failed_analysis,
    ):
        response = client.post("/ai/analyze_dividend_event", json=_request_body())

    assert response.status_code == 502
    assert response.json()["data"]["analysis_status"] == "Failed"
    assert response.json()["data"]["historical_baseline"]["sample_count"] == 5


def test_sync_dividend_analysis_preserves_validation_warnings():
    async def warned_analysis(**kwargs):
        analysis_data = dividend_fixtures.complete_analysis().model_dump(mode="python")
        analysis_data.update(
            {
                "analysis_status": "CompleteWithWarnings",
                "validation_warnings": ["Application corrected assessment arithmetic."],
            }
        )
        return models_dividends.DividendEventAnalysis.model_validate(analysis_data)

    with mock.patch(
        "app.routers.ai_dividend.services_dividend.ai_analyze_div_event",
        new=warned_analysis,
    ):
        response = client.post("/ai/analyze_dividend_event", json=_request_body())

    assert response.status_code == 200
    assert response.json()["data"]["analysis_status"] == "CompleteWithWarnings"
    assert response.json()["data"]["validation_warnings"] == ["Application corrected assessment arithmetic."]


def test_async_dividend_lifecycle_returns_running_then_completed_analysis(deferred_task_store):
    with mock.patch(
        "app.routers.ai_dividend.services_dividend.ai_analyze_div_event",
        new=_analysis_for_request,
    ):
        started = client.post(
            "/ai/start_analyze_dividend_event_async",
            json=_request_body(),
        )
        task_id = started.json()["extra"]["task_id"]
        running = client.post(
            "/ai/poll_analyze_dividend_event_async",
            params={"task_id": task_id},
        )

        deferred_task_store.release()

        completed = client.post(
            "/ai/poll_analyze_dividend_event_async",
            params={"task_id": task_id},
        )
        duplicate = client.post(
            "/ai/start_analyze_dividend_event_async",
            json=_request_body(),
        )

    assert started.status_code == 202
    assert running.status_code == 202
    assert completed.status_code == 200
    assert completed.json()["extra"] == {"task_id": task_id, "state": "COMPLETED"}
    assert completed.json()["data"]["event"]["symbol"] == "ASX:CBA"
    assert duplicate.json() == completed.json()


def test_async_dividend_start_distinguishes_missing_and_invalid_bodies():
    missing = client.post("/ai/start_analyze_dividend_event_async")
    invalid = client.post(
        "/ai/start_analyze_dividend_event_async",
        json=_request_body(dividend_amount=0),
    )

    assert missing.status_code == 400
    assert missing.json()["status"] == 400
    assert invalid.status_code == 422
    assert isinstance(invalid.json()["detail"], list)


def test_async_failed_analysis_retains_baseline_data(deferred_task_store):
    async def failed_analysis(**kwargs):
        return dividend_fixtures.failed_analysis()

    with mock.patch(
        "app.routers.ai_dividend.services_dividend.ai_analyze_div_event",
        new=failed_analysis,
    ):
        started = client.post(
            "/ai/start_analyze_dividend_event_async",
            json=_request_body(),
        )
        task_id = started.json()["extra"]["task_id"]
        deferred_task_store.release()
        failed = client.post(
            "/ai/poll_analyze_dividend_event_async",
            params={"task_id": task_id},
        )
        duplicate = client.post(
            "/ai/start_analyze_dividend_event_async",
            json=_request_body(),
        )

    assert failed.status_code == 502
    assert failed.json()["extra"] == {"task_id": task_id, "state": "FAILED"}
    assert failed.json()["data"]["analysis_status"] == "Failed"
    assert failed.json()["data"]["historical_baseline"]["sample_count"] == 5
    assert duplicate.json() == failed.json()


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (services_dividend.DividendEventInputError("invalid event"), 400),
        (services_dividend.DividendEventInsufficientDataError("insufficient history"), 422),
        (services_dividend.DividendEventAIError("analysis unavailable"), 502),
        (ai_helper.LLMRateLimitError("rate-limit budget exhausted"), 502),
        (RuntimeError("unexpected failure"), 500),
    ],
)
def test_async_raised_failures_are_pollable_without_partial_data(
    deferred_task_store,
    error,
    expected_status,
):
    async def fail(**kwargs):
        raise error

    with mock.patch(
        "app.routers.ai_dividend.services_dividend.ai_analyze_div_event",
        new=fail,
    ):
        started = client.post(
            "/ai/start_analyze_dividend_event_async",
            json=_request_body(),
        )
        task_id = started.json()["extra"]["task_id"]
        deferred_task_store.release()
        failed = client.post(
            "/ai/poll_analyze_dividend_event_async",
            params={"task_id": task_id},
        )

    assert failed.status_code == expected_status
    assert failed.json()["extra"] == {"task_id": task_id, "state": "FAILED"}
    assert "data" not in failed.json()
