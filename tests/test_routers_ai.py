"""Unit tests for app.routers.ai."""

import asyncio
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.schemas import ai_portfolio_construction as schemas_construction
from app.schemas import async_task
from app.services import msai_build_portfolio as service_build_portfolio
from app.services import portfolio_verification
from tests import portfolio_construction_fixtures

client = TestClient(app)


# ===========================================================================
# GET /ai/vendors
# ===========================================================================


class TestGetVendors:
    """Tests for GET /ai/vendors endpoint."""

    def test_returns_vendors_list(self):
        resp = client.get("/ai/vendors")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == 200
        assert body["message"] == "ok"
        assert isinstance(body["data"], dict)


# ===========================================================================
# POST /ai/build_portfolio
# ===========================================================================


class TestBuildPortfolio:
    """Tests for POST /ai/build_portfolio endpoint."""

    @patch(
        "app.routers.ai_portfolio_construction.service_build_portfolio.ai_build_portfolio",
        new_callable=AsyncMock,
    )
    def test_success(self, mock_build):
        mock_build.return_value = portfolio_construction_fixtures.construction()
        resp = client.post(
            "/ai/build_portfolio",
            json={
                "country": "US",
                "investor_theme": "Durable growth with moderate risk.",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == 200
        assert body["data"]["construction_mode"] == "Scratch"
        assert body["data"]["target_portfolio"][0]["allocation"] == 0.4
        assert "analysis" not in body["data"]
        assert "rebalance_plan" not in body["data"]

    @patch(
        "app.routers.ai_portfolio_construction.service_build_portfolio.ai_build_portfolio",
        new_callable=AsyncMock,
    )
    def test_success_preserves_null_action_plan(self, mock_build):
        mock_build.return_value = portfolio_construction_fixtures.construction(action_plan_available=False)

        resp = client.post(
            "/ai/build_portfolio",
            json={
                "country": "US",
                "investor_theme": "Durable growth with moderate risk.",
            },
        )

        assert resp.status_code == 200
        assert resp.json()["data"]["action_plan"] is None

    @patch(
        "app.routers.ai_portfolio_construction.service_build_portfolio.ai_build_portfolio",
        new_callable=AsyncMock,
    )
    def test_passes_existing_positions(self, mock_build):
        mock_build.return_value = portfolio_construction_fixtures.construction(mode="Seeded")
        positions = [{"ticker": "AAPL", "num_shares": 10, "market_price": 150.0}]
        resp = client.post(
            "/ai/build_portfolio",
            json={
                "country": "US",
                "investor_theme": "Growth focused",
                "current_allocation": positions,
            },
        )
        assert resp.status_code == 200
        call_kwargs = mock_build.call_args.kwargs
        assert len(call_kwargs["portfolio"]) == 1
        assert call_kwargs["portfolio"][0].ticker == "AAPL"
        assert call_kwargs["investor_theme"] == "Growth focused"

    def test_requires_country_and_investor_theme(self):
        assert client.post("/ai/build_portfolio", json={}).status_code == 422
        assert (
            client.post(
                "/ai/build_portfolio",
                json={"country": "US"},
            ).status_code
            == 422
        )

    def test_rejects_blank_theme_duplicates_and_removed_rebalance_plan(self):
        blank_theme = {
            "country": "US",
            "investor_theme": "   ",
        }
        duplicates = {
            "country": "US",
            "investor_theme": "Growth",
            "current_allocation": [
                {"ticker": "aapl", "num_shares": 1},
                {"ticker": "AAPL", "num_shares": 2},
            ],
        }
        removed_field = {
            "country": "US",
            "investor_theme": "Growth",
            "rebalance_plan": True,
        }

        assert client.post("/ai/build_portfolio", json=blank_theme).status_code == 422
        assert client.post("/ai/build_portfolio", json=duplicates).status_code == 422
        assert client.post("/ai/build_portfolio", json=removed_field).status_code == 422

    @patch(
        "app.routers.ai_portfolio_construction.service_build_portfolio.ai_build_portfolio",
        new_callable=AsyncMock,
        side_effect=portfolio_verification.PortfolioInputError("Unknown ticker"),
    )
    def test_maps_input_failure_to_422(self, mock_build):
        response = client.post(
            "/ai/build_portfolio",
            json={"country": "US", "investor_theme": "Growth"},
        )

        assert response.status_code == 422
        assert response.json()["message"] == "Unknown ticker"
        mock_build.assert_awaited_once()

    @patch(
        "app.routers.ai_portfolio_construction.service_build_portfolio.ai_build_portfolio",
        new_callable=AsyncMock,
        side_effect=service_build_portfolio.PortfolioConstructionAIError("Research failed"),
    )
    def test_maps_ai_failure_to_502(self, mock_build):
        response = client.post(
            "/ai/build_portfolio",
            json={"country": "US", "investor_theme": "Growth"},
        )

        assert response.status_code == 502
        assert response.json()["message"] == "Research failed"
        mock_build.assert_awaited_once()


# ===========================================================================
# POST /ai/build_portfolio_async
# ===========================================================================


class TestBuildPortfolioAsync:
    """Tests for POST /ai/build_portfolio_async endpoint."""

    def test_starts_task(self):
        with (
            patch("app.routers.async_task._generate_task_id", return_value="task-789"),
            patch("app.routers.async_task.cache.set", new_callable=AsyncMock, return_value=True) as mock_cache_set,
            patch(
                "app.routers.ai_portfolio_construction._run_build_portfolio_task",
                new_callable=AsyncMock,
            ) as mock_run_task,
        ):
            resp = client.post(
                "/ai/build_portfolio_async",
                json={
                    "country": "US",
                    "investor_theme": "Growth focused",
                    "current_allocation": [
                        {
                            "ticker": "AAPL",
                            "num_shares": 10,
                            "avg_price": 150.0,
                            "target_allocation": 0.5,
                        }
                    ],
                },
            )

        assert resp.status_code == 202
        assert resp.json() == {
            "status": 202,
            "message": "Task started",
            "extra": {"task_id": "task-789", "state": async_task.TASK_STATE_RUNNING},
        }
        mock_cache_set.assert_awaited_once_with(
            "task-789",
            {"task_type": "build_portfolio", "state": async_task.TASK_STATE_RUNNING},
            ttl=3600,
        )
        mock_run_task.assert_awaited_once()
        task_id, task_req = mock_run_task.await_args.args
        assert task_id == "task-789"
        assert task_req.country == "US"
        assert task_req.investor_theme == "Growth focused"
        assert task_req.current_allocation[0].ticker == "AAPL"

    def test_requires_body_when_starting_task(self):
        resp = client.post("/ai/build_portfolio_async")

        assert resp.status_code == 400
        assert resp.json() == {
            "status": 400,
            "message": "Request body is required when starting a task",
        }

    def test_requires_country_when_starting_task(self):
        resp = client.post("/ai/build_portfolio_async", json={})

        assert resp.status_code == 422

    def test_poll_returns_running_status(self):
        task_entry = {"task_type": "build_portfolio", "state": async_task.TASK_STATE_RUNNING}
        with patch(
            "app.routers.async_task.cache.get", new_callable=AsyncMock, return_value=task_entry
        ) as mock_cache_get:
            resp = client.post("/ai/build_portfolio_async", params={"task_id": "task-789"})

        assert resp.status_code == 202
        assert resp.json()["message"] == "Task is running"
        assert resp.json()["extra"] == {"task_id": "task-789", "state": async_task.TASK_STATE_RUNNING}
        mock_cache_get.assert_awaited_once_with("task-789")

    def test_poll_returns_404_for_missing_task(self):
        with patch("app.routers.async_task.cache.get", new_callable=AsyncMock, return_value=None):
            resp = client.post("/ai/build_portfolio_async", params={"task_id": "missing"})

        assert resp.status_code == 404
        assert resp.json() == {"status": 404, "message": "Task not found"}

    def test_poll_returns_completed_result(self):
        construction = portfolio_construction_fixtures.construction(action_plan_available=False)
        task_entry = {
            "task_type": "build_portfolio",
            "state": async_task.TASK_STATE_COMPLETED,
            "result": {
                "status": 200,
                "message": "ok",
                "data": construction.model_dump(mode="json"),
            },
        }
        with patch("app.routers.async_task.cache.get", new_callable=AsyncMock, return_value=task_entry):
            resp = client.post("/ai/build_portfolio_async", params={"task_id": "task-789"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == 200
        assert body["data"]["construction_mode"] == "Scratch"
        assert body["data"]["action_plan"] is None
        assert body["extra"] == {"task_id": "task-789", "state": async_task.TASK_STATE_COMPLETED}

    def test_poll_returns_failed_status(self):
        task_entry = {
            "task_type": "build_portfolio",
            "state": async_task.TASK_STATE_FAILED,
            "status": 422,
            "message": "Unknown ticker",
        }
        with patch("app.routers.async_task.cache.get", new_callable=AsyncMock, return_value=task_entry):
            resp = client.post("/ai/build_portfolio_async", params={"task_id": "task-789"})

        assert resp.status_code == 422
        assert resp.json() == {
            "status": 422,
            "message": "Unknown ticker",
            "extra": {"task_id": "task-789", "state": async_task.TASK_STATE_FAILED},
        }

    def test_background_task_caches_result(self):
        from app.routers import ai_portfolio_construction as router_construction

        req = schemas_construction.BuildPortfolioRequest(
            country="US",
            investor_theme="Growth focused",
        )
        result = schemas_construction.BuildPortfolioResponse(
            status=200,
            message="ok",
            data=portfolio_construction_fixtures.construction(),
        )
        with (
            patch(
                "app.routers.ai_portfolio_construction._get_build_portfolio_result",
                new_callable=AsyncMock,
                return_value=result,
            ),
            patch("app.routers.async_task.cache.set", new_callable=AsyncMock, return_value=True) as mock_cache_set,
        ):
            asyncio.run(router_construction._run_build_portfolio_task("task-789", req))

        mock_cache_set.assert_awaited_once_with(
            "task-789",
            {
                "task_type": "build_portfolio",
                "state": async_task.TASK_STATE_COMPLETED,
                "result": {
                    "status": 200,
                    "message": "ok",
                    "data": result.data.model_dump(mode="json"),
                    "extra": None,
                },
            },
            ttl=3600,
        )

    def test_background_task_caches_failure(self):
        from app.routers import ai_portfolio_construction as router_construction

        req = schemas_construction.BuildPortfolioRequest(
            country="US",
            investor_theme="Growth focused",
        )
        with (
            patch(
                "app.routers.ai_portfolio_construction._get_build_portfolio_result",
                new_callable=AsyncMock,
                side_effect=RuntimeError("LLM unavailable"),
            ),
            patch("app.routers.async_task.cache.set", new_callable=AsyncMock, return_value=True) as mock_cache_set,
        ):
            asyncio.run(router_construction._run_build_portfolio_task("task-789", req))

        mock_cache_set.assert_awaited_once_with(
            "task-789",
            {
                "task_type": "build_portfolio",
                "state": async_task.TASK_STATE_FAILED,
                "status": 500,
                "message": "Task failed",
            },
            ttl=3600,
        )
