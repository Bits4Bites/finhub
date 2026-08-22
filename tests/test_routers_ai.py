"""Unit tests for app.routers.ai."""

import asyncio
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.models.ai import AnalysisResult, AnalyzePortfolioResult
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
# POST /ai/analyze_ticker
# ===========================================================================


class TestAnalyzeTicker:
    """Tests for POST /ai/analyze_ticker endpoint."""

    @patch(
        "app.routers.ai.service_analyze_ticker.ai_analyze_ticker",
        new_callable=AsyncMock,
    )
    def test_success(self, mock_analyze):
        mock_analyze.return_value = AnalysisResult(
            llm_error=False,
            analysis="AAPL looks bullish",
        )
        resp = client.post("/ai/analyze_ticker", json={"symbol": "NASDAQ:AAPL"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == 200
        assert body["data"]["analysis"] == "AAPL looks bullish"
        mock_analyze.assert_called_once()
        assert mock_analyze.call_args.kwargs["symbol"] == "NASDAQ:AAPL"

    @patch(
        "app.routers.ai.service_analyze_ticker.ai_analyze_ticker",
        new_callable=AsyncMock,
    )
    def test_returns_400_when_service_returns_none(self, mock_analyze):
        mock_analyze.return_value = None
        resp = client.post("/ai/analyze_ticker", json={"symbol": "INVALID"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == 400
        assert "Invalid" in body["message"] or "failed" in body["message"]

    @patch(
        "app.routers.ai.service_analyze_ticker.ai_analyze_ticker",
        new_callable=AsyncMock,
    )
    def test_passes_intent_to_service(self, mock_analyze):
        mock_analyze.return_value = AnalysisResult(llm_error=False, analysis="result")
        resp = client.post(
            "/ai/analyze_ticker",
            json={"symbol": "ASX:CBA", "intent": "focus on dividends"},
        )
        assert resp.status_code == 200
        mock_analyze.assert_called_once_with(symbol="ASX:CBA", intent="focus on dividends")


# ===========================================================================
# POST /ai/analyze_ticker_async
# ===========================================================================


class TestAnalyzeTickerAsync:
    """Tests for POST /ai/analyze_ticker_async endpoint."""

    def test_starts_task(self):
        with (
            patch("app.routers.async_task.uuid.uuid4", return_value="task-456"),
            patch("app.routers.async_task.cache.set", new_callable=AsyncMock, return_value=True) as mock_cache_set,
            patch("app.routers.ai._run_analyze_ticker_task", new_callable=AsyncMock) as mock_run_task,
        ):
            resp = client.post(
                "/ai/analyze_ticker_async",
                json={"symbol": "NASDAQ:AAPL", "intent": "Growth outlook"},
            )

        assert resp.status_code == 202
        assert resp.json() == {
            "status": 202,
            "message": "Task started",
            "extra": {"task_id": "task-456", "state": async_task.TASK_STATE_RUNNING},
        }
        mock_cache_set.assert_awaited_once_with(
            "task-456",
            {"task_type": "analyze_ticker", "state": async_task.TASK_STATE_RUNNING},
            ttl=3600,
        )
        mock_run_task.assert_awaited_once_with(
            "task-456",
            "NASDAQ:AAPL",
            "Growth outlook",
        )

    def test_requires_symbol_when_starting_task(self):
        resp = client.post("/ai/analyze_ticker_async", json={})

        assert resp.status_code == 400
        assert resp.json() == {
            "status": 400,
            "message": "Symbol is required when starting a task",
        }

    def test_poll_returns_running_status(self):
        task_entry = {"task_type": "analyze_ticker", "state": async_task.TASK_STATE_RUNNING}
        with patch(
            "app.routers.async_task.cache.get", new_callable=AsyncMock, return_value=task_entry
        ) as mock_cache_get:
            resp = client.post("/ai/analyze_ticker_async", params={"task_id": "task-456"})

        assert resp.status_code == 202
        assert resp.json()["message"] == "Task is running"
        assert resp.json()["extra"] == {"task_id": "task-456", "state": async_task.TASK_STATE_RUNNING}
        mock_cache_get.assert_awaited_once_with("task-456")

    def test_poll_returns_404_for_missing_task(self):
        with patch("app.routers.async_task.cache.get", new_callable=AsyncMock, return_value=None):
            resp = client.post("/ai/analyze_ticker_async", params={"task_id": "missing"})

        assert resp.status_code == 404
        assert resp.json() == {"status": 404, "message": "Task not found"}

    def test_poll_returns_completed_result(self):
        task_entry = {
            "task_type": "analyze_ticker",
            "state": async_task.TASK_STATE_COMPLETED,
            "result": {
                "status": 200,
                "message": "ok",
                "data": {
                    "llm_error": False,
                    "analysis": "AAPL looks bullish",
                },
            },
        }
        with patch("app.routers.async_task.cache.get", new_callable=AsyncMock, return_value=task_entry):
            resp = client.post("/ai/analyze_ticker_async", params={"task_id": "task-456"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == 200
        assert body["data"]["analysis"] == "AAPL looks bullish"
        assert body["extra"] == {"task_id": "task-456", "state": async_task.TASK_STATE_COMPLETED}

    def test_poll_returns_failed_status(self):
        task_entry = {
            "task_type": "analyze_ticker",
            "state": async_task.TASK_STATE_FAILED,
            "message": "Task failed",
        }
        with patch("app.routers.async_task.cache.get", new_callable=AsyncMock, return_value=task_entry):
            resp = client.post("/ai/analyze_ticker_async", params={"task_id": "task-456"})

        assert resp.status_code == 500
        assert resp.json() == {
            "status": 500,
            "message": "Task failed",
            "extra": {"task_id": "task-456", "state": async_task.TASK_STATE_FAILED},
        }

    def test_background_task_caches_result(self):
        from app.routers import ai
        from app.schemas import ai as schemas_ai

        result = schemas_ai.AnalysisResponse(
            status=200,
            message="ok",
            data=AnalysisResult(llm_error=False, analysis="AAPL looks bullish"),
        )
        with (
            patch(
                "app.routers.ai._get_analyze_ticker_result",
                new_callable=AsyncMock,
                return_value=result,
            ),
            patch("app.routers.async_task.cache.set", new_callable=AsyncMock, return_value=True) as mock_cache_set,
        ):
            asyncio.run(ai._run_analyze_ticker_task("task-456", "NASDAQ:AAPL", "Growth outlook"))

        mock_cache_set.assert_awaited_once_with(
            "task-456",
            {
                "task_type": "analyze_ticker",
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
        from app.routers import ai

        with (
            patch(
                "app.routers.ai._get_analyze_ticker_result",
                new_callable=AsyncMock,
                side_effect=RuntimeError("LLM unavailable"),
            ),
            patch("app.routers.async_task.cache.set", new_callable=AsyncMock, return_value=True) as mock_cache_set,
        ):
            asyncio.run(ai._run_analyze_ticker_task("task-456", "NASDAQ:AAPL", "Growth outlook"))

        mock_cache_set.assert_awaited_once_with(
            "task-456",
            {
                "task_type": "analyze_ticker",
                "state": async_task.TASK_STATE_FAILED,
                "message": "Task failed",
            },
            ttl=3600,
        )


# ===========================================================================
# POST /ai/build_portfolio
# ===========================================================================


class TestBuildPortfolio:
    """Tests for POST /ai/build_portfolio endpoint."""

    def test_routes_are_owned_by_dedicated_router_module(self):
        route_modules = {
            route.path: route.endpoint.__module__
            for route in app.routes
            if getattr(route, "path", None) in {"/ai/build_portfolio", "/ai/build_portfolio_async"}
        }

        assert route_modules == {
            "/ai/build_portfolio": "app.routers.ai_portfolio_construction",
            "/ai/build_portfolio_async": "app.routers.ai_portfolio_construction",
        }

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

    def test_openapi_uses_dedicated_construction_contract(self):
        paths = app.openapi()["paths"]
        operation = paths["/ai/build_portfolio"]["post"]
        request_ref = operation["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        response_ref = operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]

        assert request_ref.endswith("/BuildPortfolioRequest")
        assert response_ref.endswith("/BuildPortfolioResponse")
        assert {"200", "422", "502"} <= set(operation["responses"])
        assert {"200", "202", "404", "422", "500", "502"} <= set(
            paths["/ai/build_portfolio_async"]["post"]["responses"]
        )


# ===========================================================================
# POST /ai/build_portfolio_async
# ===========================================================================


class TestBuildPortfolioAsync:
    """Tests for POST /ai/build_portfolio_async endpoint."""

    def test_starts_task(self):
        with (
            patch("app.routers.async_task.uuid.uuid4", return_value="task-789"),
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
        construction = portfolio_construction_fixtures.construction()
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


class TestAnalyzePortfolio:
    """Tests for POST /ai/analyze_portfolio endpoint."""

    @patch(
        "app.routers.ai.service_review_portfolio.ai_review_portfolio",
        new_callable=AsyncMock,
    )
    def test_with_positions_calls_review(self, mock_review):
        mock_review.return_value = AnalyzePortfolioResult(
            llm_error=False,
            analysis="Well diversified",
            rebalance_plan="Sell 10 CBA.AX shares",
        )
        positions = [{"ticker": "CBA.AX", "num_shares": 100, "market_price": 120.0}]
        resp = client.post(
            "/ai/analyze_portfolio",
            json={
                "country": "AU",
                "current_allocation": positions,
                "rebalance_plan": True,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == 200
        assert body["data"]["analysis"] == "Well diversified"
        assert body["data"]["rebalance_plan"] == "Sell 10 CBA.AX shares"
        mock_review.assert_called_once()
        assert mock_review.call_args.kwargs["rebalance_plan"] is True

    @patch(
        "app.routers.ai.service_build_portfolio.ai_build_portfolio",
        new_callable=AsyncMock,
    )
    def test_without_positions_calls_build(self, mock_build):
        mock_build.return_value = portfolio_construction_fixtures.construction()
        resp = client.post(
            "/ai/analyze_portfolio",
            json={
                "country": "US",
                "investor_theme": "Durable growth with moderate risk.",
                "current_allocation": [],
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["construction_mode"] == "Scratch"
        mock_build.assert_called_once()
        assert mock_build.call_args.kwargs["portfolio"] == []

    @patch(
        "app.routers.ai.service_build_portfolio.ai_build_portfolio",
        new_callable=AsyncMock,
    )
    def test_returns_400_when_service_fails(self, mock_build):
        mock_build.return_value = None
        resp = client.post(
            "/ai/analyze_portfolio",
            json={"country": "AU", "investor_theme": "Balanced growth"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == 400

    @patch(
        "app.routers.ai.service_review_portfolio.ai_review_portfolio",
        new_callable=AsyncMock,
    )
    def test_passes_investor_theme(self, mock_review):
        mock_review.return_value = AnalyzePortfolioResult(llm_error=False, analysis="result")
        positions = [{"ticker": "BHP.AX", "num_shares": 50, "market_price": 45.0}]
        resp = client.post(
            "/ai/analyze_portfolio",
            json={
                "country": "AU",
                "current_allocation": positions,
                "investor_theme": "Growth focused",
            },
        )
        assert resp.status_code == 200
        assert mock_review.call_args.kwargs["investor_theme"] == "Growth focused"

    def test_requires_country(self):
        resp = client.post("/ai/analyze_portfolio", json={})

        assert resp.status_code == 422

    def test_requires_investor_theme_for_construction_branch(self):
        resp = client.post(
            "/ai/analyze_portfolio",
            json={"country": "US", "current_allocation": []},
        )

        assert resp.status_code == 422
        assert "Investor theme is required" in resp.json()["message"]


# ===========================================================================
# POST /ai/analyze_portfolio_async
# ===========================================================================


class TestAnalyzePortfolioAsync:
    """Tests for POST /ai/analyze_portfolio_async endpoint."""

    def test_starts_task(self):
        with (
            patch("app.routers.async_task.uuid.uuid4", return_value="task-analyze"),
            patch("app.routers.async_task.cache.set", new_callable=AsyncMock, return_value=True) as mock_cache_set,
            patch("app.routers.ai._run_analyze_portfolio_task", new_callable=AsyncMock) as mock_run_task,
        ):
            resp = client.post(
                "/ai/analyze_portfolio_async",
                json={
                    "country": "AU",
                    "investor_theme": "Growth focused",
                    "rebalance_plan": True,
                    "current_allocation": [
                        {
                            "ticker": "CBA.AX",
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
            "extra": {"task_id": "task-analyze", "state": async_task.TASK_STATE_RUNNING},
        }
        mock_cache_set.assert_awaited_once_with(
            "task-analyze",
            {"task_type": "analyze_portfolio", "state": async_task.TASK_STATE_RUNNING},
            ttl=3600,
        )
        mock_run_task.assert_awaited_once()
        task_id, task_req = mock_run_task.await_args.args
        assert task_id == "task-analyze"
        assert task_req.country == "AU"
        assert task_req.investor_theme == "Growth focused"
        assert task_req.rebalance_plan is True
        assert task_req.current_allocation[0].ticker == "CBA.AX"

    def test_requires_body_when_starting_task(self):
        resp = client.post("/ai/analyze_portfolio_async")

        assert resp.status_code == 400
        assert resp.json() == {
            "status": 400,
            "message": "Request body is required when starting a task",
        }

    def test_requires_country_when_starting_task(self):
        resp = client.post("/ai/analyze_portfolio_async", json={})

        assert resp.status_code == 422

    def test_poll_returns_running_status(self):
        task_entry = {"task_type": "analyze_portfolio", "state": async_task.TASK_STATE_RUNNING}
        with patch(
            "app.routers.async_task.cache.get", new_callable=AsyncMock, return_value=task_entry
        ) as mock_cache_get:
            resp = client.post("/ai/analyze_portfolio_async", params={"task_id": "task-analyze"})

        assert resp.status_code == 202
        assert resp.json()["message"] == "Task is running"
        assert resp.json()["extra"] == {"task_id": "task-analyze", "state": async_task.TASK_STATE_RUNNING}
        mock_cache_get.assert_awaited_once_with("task-analyze")

    def test_poll_returns_404_for_missing_task(self):
        with patch("app.routers.async_task.cache.get", new_callable=AsyncMock, return_value=None):
            resp = client.post("/ai/analyze_portfolio_async", params={"task_id": "missing"})

        assert resp.status_code == 404
        assert resp.json() == {"status": 404, "message": "Task not found"}

    def test_poll_returns_completed_result(self):
        task_entry = {
            "task_type": "analyze_portfolio",
            "state": async_task.TASK_STATE_COMPLETED,
            "result": {
                "status": 200,
                "message": "ok",
                "data": {
                    "llm_error": False,
                    "analysis": "Well diversified",
                    "rebalance_plan": "No rebalance needed",
                },
            },
        }
        with patch("app.routers.async_task.cache.get", new_callable=AsyncMock, return_value=task_entry):
            resp = client.post("/ai/analyze_portfolio_async", params={"task_id": "task-analyze"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == 200
        assert body["data"]["analysis"] == "Well diversified"
        assert body["data"]["rebalance_plan"] == "No rebalance needed"
        assert body["extra"] == {"task_id": "task-analyze", "state": async_task.TASK_STATE_COMPLETED}

    def test_poll_returns_failed_status(self):
        task_entry = {
            "task_type": "analyze_portfolio",
            "state": async_task.TASK_STATE_FAILED,
            "message": "Task failed",
        }
        with patch("app.routers.async_task.cache.get", new_callable=AsyncMock, return_value=task_entry):
            resp = client.post("/ai/analyze_portfolio_async", params={"task_id": "task-analyze"})

        assert resp.status_code == 500
        assert resp.json() == {
            "status": 500,
            "message": "Task failed",
            "extra": {"task_id": "task-analyze", "state": async_task.TASK_STATE_FAILED},
        }

    def test_background_task_caches_result(self):
        from app.routers import ai
        from app.schemas import ai as schemas_ai

        req = schemas_ai.AnalyzePortfolioRequest(country="AU")
        result = schemas_ai.AnalyzePortfolioResponse(
            status=200,
            message="ok",
            data=AnalyzePortfolioResult(llm_error=False, analysis="New portfolio"),
        )
        with (
            patch(
                "app.routers.ai._get_analyze_portfolio_result",
                new_callable=AsyncMock,
                return_value=result,
            ),
            patch("app.routers.async_task.cache.set", new_callable=AsyncMock, return_value=True) as mock_cache_set,
        ):
            asyncio.run(ai._run_analyze_portfolio_task("task-analyze", req))

        mock_cache_set.assert_awaited_once_with(
            "task-analyze",
            {
                "task_type": "analyze_portfolio",
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
        from app.routers import ai
        from app.schemas import ai as schemas_ai

        req = schemas_ai.AnalyzePortfolioRequest(country="AU")
        with (
            patch(
                "app.routers.ai._get_analyze_portfolio_result",
                new_callable=AsyncMock,
                side_effect=RuntimeError("LLM unavailable"),
            ),
            patch("app.routers.async_task.cache.set", new_callable=AsyncMock, return_value=True) as mock_cache_set,
        ):
            asyncio.run(ai._run_analyze_portfolio_task("task-analyze", req))

        mock_cache_set.assert_awaited_once_with(
            "task-analyze",
            {
                "task_type": "analyze_portfolio",
                "state": async_task.TASK_STATE_FAILED,
                "message": "Task failed",
            },
            ttl=3600,
        )
