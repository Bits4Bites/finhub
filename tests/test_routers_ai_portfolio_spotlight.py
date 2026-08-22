import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas import async_task
from tests import portfolio_spotlight_fixtures

client = TestClient(app)


def _request_body() -> dict[str, object]:
    return {
        "country": "US",
        "investor_theme": "Growth focused",
        "current_allocation": [
            {
                "ticker": "NASDAQ:AAPL",
                "num_shares": 10,
                "avg_price": 150,
                "market_price": 190,
                "target_allocation": 0.6,
                "tags": "growth",
            }
        ],
    }


def test_post_returns_structured_spotlight_analysis():
    with patch(
        "app.routers.ai_portfolio_spotlight.services_spotlight.ai_spotlight_portfolio",
        new_callable=AsyncMock,
        return_value=portfolio_spotlight_fixtures.analysis(),
    ):
        response = client.post("/ai/spotlight_portfolio", json=_request_body())

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["portfolio_empty"] is False
    assert data["risks"][0]["level"] == "Critical"
    assert data["risks"][0]["action_timing"] == "AsSoonAsPossibleWithinOneWeek"
    assert data["rebalance_recommended"] == "YES"
    assert "analysis" not in data


def test_post_empty_portfolio_returns_structured_empty_flag():
    with patch(
        "app.routers.ai_portfolio_spotlight.services_spotlight.ai_spotlight_portfolio",
        new_callable=AsyncMock,
        return_value=portfolio_spotlight_fixtures.analysis(portfolio_empty=True),
    ) as mock_spotlight:
        response = client.post(
            "/ai/spotlight_portfolio",
            json={"country": "AU", "current_allocation": []},
        )

    assert response.status_code == 200
    assert response.json()["data"]["portfolio_empty"] is True
    mock_spotlight.assert_awaited_once()


@pytest.mark.parametrize("investor_theme", [None, "", "   "])
def test_post_accepts_missing_or_blank_investor_theme(investor_theme):
    request = _request_body()
    if investor_theme is None:
        request.pop("investor_theme")
    else:
        request["investor_theme"] = investor_theme

    with patch(
        "app.routers.ai_portfolio_spotlight.services_spotlight.ai_spotlight_portfolio",
        new_callable=AsyncMock,
        return_value=portfolio_spotlight_fixtures.analysis(),
    ) as mock_spotlight:
        response = client.post("/ai/spotlight_portfolio", json=request)

    assert response.status_code == 200
    assert mock_spotlight.await_args.kwargs["investor_theme"] is None


def test_post_rejects_overlong_country_and_ticker():
    country_request = _request_body()
    country_request["country"] = "A" * 65
    ticker_request = _request_body()
    ticker_request["current_allocation"][0]["ticker"] = "A" * 33

    assert client.post("/ai/spotlight_portfolio", json=country_request).status_code == 422
    assert client.post("/ai/spotlight_portfolio", json=ticker_request).status_code == 422


def test_openapi_reuses_shared_holding_and_optional_theme_contracts():
    schemas = app.openapi()["components"]["schemas"]
    spotlight_request = schemas["PortfolioSpotlightRequest"]
    analyze_request = schemas["AnalyzePortfolioRequest"]

    assert spotlight_request["properties"]["current_allocation"]["items"]["$ref"].endswith("/PortfolioHolding")
    assert analyze_request["properties"]["current_allocation"]["items"]["$ref"].endswith("/PortfolioHolding")
    assert "PortfolioSpotlightHolding" not in schemas
    assert "investor_theme" not in spotlight_request["required"]
    assert "default" not in spotlight_request["properties"]["investor_theme"]


def test_post_rejects_removed_rebalance_plan_input():
    request = _request_body()
    request["rebalance_plan"] = True

    response = client.post("/ai/spotlight_portfolio", json=request)

    assert response.status_code == 422


def test_post_maps_portfolio_validation_failure_to_422():
    from app.services import msai_spotlight_portfolio as service

    with patch(
        "app.routers.ai_portfolio_spotlight.services_spotlight.ai_spotlight_portfolio",
        new_callable=AsyncMock,
        side_effect=service.PortfolioSpotlightInputError("Unknown ticker"),
    ):
        response = client.post("/ai/spotlight_portfolio", json=_request_body())

    assert response.status_code == 422
    assert response.json()["message"] == "Unknown ticker"


def test_post_maps_ai_failure_to_502():
    from app.services import msai_spotlight_portfolio as service

    with patch(
        "app.routers.ai_portfolio_spotlight.services_spotlight.ai_spotlight_portfolio",
        new_callable=AsyncMock,
        side_effect=service.PortfolioSpotlightAIError("Assessment failed"),
    ):
        response = client.post("/ai/spotlight_portfolio", json=_request_body())

    assert response.status_code == 502
    assert response.json()["message"] == "Assessment failed"


def test_async_start_uses_dedicated_request_schema():
    with (
        patch("app.routers.async_task.uuid.uuid4", return_value="task-spotlight"),
        patch(
            "app.routers.async_task.cache.set",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_cache_set,
        patch(
            "app.routers.ai_portfolio_spotlight._run_task",
            new_callable=AsyncMock,
        ) as mock_run_task,
    ):
        response = client.post("/ai/spotlight_portfolio_async", json=_request_body())

    assert response.status_code == 202
    assert response.json() == {
        "status": 202,
        "message": "Task started",
        "extra": {
            "task_id": "task-spotlight",
            "state": async_task.TASK_STATE_RUNNING,
        },
    }
    mock_cache_set.assert_awaited_once_with(
        "task-spotlight",
        {
            "task_type": "spotlight_portfolio",
            "state": async_task.TASK_STATE_RUNNING,
        },
        ttl=3600,
    )
    task_id, request = mock_run_task.await_args.args
    assert task_id == "task-spotlight"
    assert request.current_allocation[0].ticker == "NASDAQ:AAPL"


def test_async_poll_returns_running_state():
    task_entry = {
        "task_type": "spotlight_portfolio",
        "state": async_task.TASK_STATE_RUNNING,
    }
    with patch(
        "app.routers.async_task.cache.get",
        new_callable=AsyncMock,
        return_value=task_entry,
    ):
        response = client.post(
            "/ai/spotlight_portfolio_async",
            params={"task_id": "task-spotlight"},
        )

    assert response.status_code == 202
    assert response.json()["extra"]["state"] == async_task.TASK_STATE_RUNNING


def test_async_poll_returns_completed_structured_result():
    from app.schemas import ai_portfolio_spotlight as schemas_spotlight

    result = schemas_spotlight.PortfolioSpotlightResponse(
        status=200,
        message="ok",
        data=portfolio_spotlight_fixtures.analysis(),
    )
    task_entry = {
        "task_type": "spotlight_portfolio",
        "state": async_task.TASK_STATE_COMPLETED,
        "result": result.model_dump(mode="json"),
    }
    with patch(
        "app.routers.async_task.cache.get",
        new_callable=AsyncMock,
        return_value=task_entry,
    ):
        response = client.post(
            "/ai/spotlight_portfolio_async",
            params={"task_id": "task-spotlight"},
        )

    assert response.status_code == 200
    assert response.json()["data"]["rebalance_recommended"] == "YES"
    assert response.json()["extra"]["state"] == async_task.TASK_STATE_COMPLETED


def test_async_poll_preserves_failure_status():
    task_entry = {
        "task_type": "spotlight_portfolio",
        "state": async_task.TASK_STATE_FAILED,
        "status": 502,
        "message": "Assessment failed",
    }
    with patch(
        "app.routers.async_task.cache.get",
        new_callable=AsyncMock,
        return_value=task_entry,
    ):
        response = client.post(
            "/ai/spotlight_portfolio_async",
            params={"task_id": "task-spotlight"},
        )

    assert response.status_code == 502
    assert response.json()["message"] == "Assessment failed"
    assert response.json()["extra"]["state"] == async_task.TASK_STATE_FAILED


def test_background_task_caches_input_failure():
    from app.routers import ai_portfolio_spotlight as router
    from app.schemas import ai_portfolio_spotlight as schemas_spotlight

    request = schemas_spotlight.PortfolioSpotlightRequest.model_validate(_request_body())
    with (
        patch.object(
            router,
            "_analyze",
            new_callable=AsyncMock,
            side_effect=router.HTTPException(status_code=422, detail="Unknown ticker"),
        ),
        patch("app.routers.async_task.cache.set", new_callable=AsyncMock, return_value=True) as mock_cache_set,
    ):
        asyncio.run(router._run_task("task-spotlight", request))

    mock_cache_set.assert_awaited_once_with(
        "task-spotlight",
        {
            "task_type": "spotlight_portfolio",
            "state": async_task.TASK_STATE_FAILED,
            "status": 422,
            "message": "Unknown ticker",
        },
        ttl=3600,
    )
