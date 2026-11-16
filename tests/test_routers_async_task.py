import asyncio
from unittest import mock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import config
from app.main import app
from app.models import event as models_event
from app.routers import async_task as router_async_task
from app.schemas.base_req_resp import BaseResponse
from app.utils import cache

client = TestClient(app)

START_EARNINGS = "/events/start_upcoming_earnings_async"
POLL_EARNINGS = "/events/poll_upcoming_earnings_async"


def _earnings_event() -> models_event.UpcomingEarningsEvent:
    return models_event.UpcomingEarningsEvent(
        symbol="NASDAQ:AAPL",
        exchange="NASDAQ",
        company_name="Apple Inc.",
        timestamp_str="2026-12-01 08:00:00-05:00",
        status="estimated",
        report_period="Q4",
    )


@pytest.fixture(autouse=True)
def disable_proxy(monkeypatch):
    monkeypatch.setattr(config.settings_finhub_proxy, "proxy_mode", "None")
    monkeypatch.setattr(config.settings_finhub_proxy, "url_web_crawl_node", "")
    monkeypatch.setattr(config.settings_finhub_proxy, "url_ai_task_node", "")


def test_http_lifecycle_runs_then_completes_and_reuses_the_terminal_task(deferred_task_store):
    service = mock.AsyncMock(return_value=[_earnings_event()])
    with mock.patch("app.routers.events.services_event.get_us_upcoming_earnings_events", new=service):
        started = client.get(START_EARNINGS, params={"country": "US", "index": "SP500"})
        task_id = started.json()["extra"]["task_id"]
        running = client.get(POLL_EARNINGS, params={"task_id": task_id})
        duplicate_running = client.get(START_EARNINGS, params={"country": "usa", "index": "sp500"})

        deferred_task_store.release()

        completed = client.get(POLL_EARNINGS, params={"task_id": f"  {task_id}  "})
        duplicate_completed = client.get(START_EARNINGS, params={"country": "United States", "index": "SP500"})

    assert started.status_code == 202
    assert isinstance(task_id, str) and task_id
    assert started.json()["extra"]["state"] == "RUNNING"
    assert running.status_code == 202
    assert running.json()["extra"] == {"task_id": task_id, "state": "RUNNING"}
    assert duplicate_running.json()["extra"] == {"task_id": task_id, "state": "RUNNING"}
    assert completed.status_code == 200
    assert completed.json()["extra"] == {"task_id": task_id, "state": "COMPLETED"}
    assert [event["symbol"] for event in completed.json()["data"]] == ["NASDAQ:AAPL"]
    assert duplicate_completed.json() == completed.json()


def test_terminal_update_restarts_the_documented_task_lifetime(deferred_task_store):
    service = mock.AsyncMock(side_effect=RuntimeError("source unavailable"))
    with mock.patch("app.routers.events.services_event.get_us_upcoming_earnings_events", new=service):
        started = client.get(START_EARNINGS, params={"country": "US"})
        task_id = started.json()["extra"]["task_id"]

        deferred_task_store.advance(9)
        deferred_task_store.release()
        deferred_task_store.advance(2)
        retained_failure = client.get(POLL_EARNINGS, params={"task_id": task_id})
        duplicate_failure = client.get(START_EARNINGS, params={"country": "US"})

        deferred_task_store.advance(9)
        expired = client.get(POLL_EARNINGS, params={"task_id": task_id})

    assert retained_failure.status_code == 500
    assert retained_failure.json()["extra"] == {"task_id": task_id, "state": "FAILED"}
    assert duplicate_failure.status_code == 500
    assert duplicate_failure.json()["extra"] == {"task_id": task_id, "state": "FAILED"}
    assert expired.status_code == 404
    assert expired.json()["status"] == 404


def test_expired_running_task_is_not_pollable_and_can_be_started_again(deferred_task_store):
    service = mock.AsyncMock(return_value=[_earnings_event()])
    with mock.patch("app.routers.events.services_event.get_us_upcoming_earnings_events", new=service):
        first = client.get(START_EARNINGS, params={"country": "US"})
        task_id = first.json()["extra"]["task_id"]
        deferred_task_store.advance(10)

        expired = client.get(POLL_EARNINGS, params={"task_id": task_id})
        restarted = client.get(START_EARNINGS, params={"country": "US"})

    assert expired.status_code == 404
    assert restarted.status_code == 202
    assert restarted.json()["extra"]["state"] == "RUNNING"


def test_polling_unknown_or_other_workflow_tasks_returns_not_found(deferred_task_store):
    service = mock.AsyncMock(return_value=[_earnings_event()])
    with mock.patch("app.routers.events.services_event.get_us_upcoming_earnings_events", new=service):
        started = client.get(START_EARNINGS, params={"country": "US"})

    unknown = client.get(POLL_EARNINGS, params={"task_id": "opaque-unknown-task"})
    other_workflow = client.get(
        "/events/poll_upcoming_dividends_async",
        params={"task_id": started.json()["extra"]["task_id"]},
    )

    assert unknown.status_code == 404
    assert other_workflow.status_code == 404


def test_cache_task_store_conforms_to_public_lifecycle_and_workflow_boundaries():
    async def exercise_store():
        await cache.clear()
        store = router_async_task.CacheTaskStore()

        task_id, created = await store.start("workflow-a", "normalized-input")
        duplicate_id, duplicate_created = await store.start("workflow-a", "normalized-input")
        running = await store.load(task_id, "workflow-a")

        completed_result = BaseResponse(status=200, message="ok", data={"value": 1})
        await store.complete(
            task_id,
            "workflow-a",
            completed_result,
            status_code=200,
            message="complete",
        )
        completed = await store.load(task_id, "workflow-a")
        terminal_id, terminal_created = await store.start("workflow-a", "normalized-input")

        other_task_id, other_created = await store.start("workflow-b", "normalized-input")
        with pytest.raises(HTTPException) as wrong_workflow:
            await store.load(task_id, "workflow-b")

        failed_result = BaseResponse(status=503, message="partial", data={"available": True})
        await store.fail(
            other_task_id,
            "workflow-b",
            status_code=299,
            message="failed",
            result=failed_result,
        )
        failed = await store.load(other_task_id, "workflow-b")
        await cache.clear()

        return {
            "task_id": task_id,
            "created": created,
            "duplicate_id": duplicate_id,
            "duplicate_created": duplicate_created,
            "running": running,
            "completed": completed,
            "completed_result": completed_result,
            "terminal_id": terminal_id,
            "terminal_created": terminal_created,
            "other_task_id": other_task_id,
            "other_created": other_created,
            "wrong_workflow_status": wrong_workflow.value.status_code,
            "failed": failed,
            "failed_result": failed_result,
        }

    outcome = asyncio.run(exercise_store())

    assert isinstance(outcome["task_id"], str) and outcome["task_id"]
    assert outcome["created"] is True
    assert outcome["duplicate_id"] == outcome["task_id"]
    assert outcome["duplicate_created"] is False
    assert outcome["running"].state == "RUNNING"
    assert outcome["completed"].state == "COMPLETED"
    assert outcome["completed"].status == 200
    assert outcome["completed"].message == "complete"
    assert outcome["completed"].result == outcome["completed_result"].model_dump(mode="json")
    assert outcome["terminal_id"] == outcome["task_id"]
    assert outcome["terminal_created"] is False
    assert outcome["other_created"] is True
    assert outcome["other_task_id"] != outcome["task_id"]
    assert outcome["wrong_workflow_status"] == 404
    assert outcome["failed"].state == "FAILED"
    assert outcome["failed"].message == "failed"
    assert outcome["failed"].result == outcome["failed_result"].model_dump(mode="json")
    assert outcome["failed"].failure_http_status == 500
