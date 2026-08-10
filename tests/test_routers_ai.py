"""Unit tests for app.routers.ai."""

import asyncio
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.models.ai import AnalysisResult, AnalyzePortfolioResult
from app.models.event import DividendEventAnalysis
from app.schemas import async_task

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
# GET /ai/analyze_dividend_event
# ===========================================================================


class TestAnalyzeDividendEvent:
    """Tests for GET /ai/analyze_dividend_event endpoint."""

    @patch(
        "app.routers.ai.service_analyze_div_event.ai_analyze_div_event",
        new_callable=AsyncMock,
    )
    def test_success(self, mock_analyze):
        mock_analyze.return_value = DividendEventAnalysis(
            symbol="CBA.AX",
            price=120.0,
            div_amount=2.5,
        )
        resp = client.get(
            "/ai/analyze_dividend_event",
            params={"symbol": "ASX:CBA", "ex_date": "2025-08-15", "div_amount": 2.5},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == 200
        assert body["data"]["symbol"] == "CBA.AX"
        assert body["data"]["div_amount"] == 2.5
        mock_analyze.assert_called_once_with(
            symbol="ASX:CBA",
            ex_date="2025-08-15",
            div_amount=2.5,
            intent=mock_analyze.call_args.kwargs["intent"],
        )

    @patch(
        "app.routers.ai.service_analyze_div_event.ai_analyze_div_event",
        new_callable=AsyncMock,
    )
    def test_returns_400_when_service_returns_none(self, mock_analyze):
        mock_analyze.return_value = None
        resp = client.get(
            "/ai/analyze_dividend_event",
            params={"symbol": "INVALID", "ex_date": "2025-08-15", "div_amount": 1.0},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == 400
        assert "Invalid" in body["message"]

    def test_missing_params_returns_422(self):
        resp = client.get("/ai/analyze_dividend_event")
        assert resp.status_code == 422


# ===========================================================================
# GET /ai/analyze_dividend_event_async
# ===========================================================================


class TestAnalyzeDividendEventAsync:
    """Tests for GET /ai/analyze_dividend_event_async endpoint."""

    def test_starts_task(self):
        with (
            patch("app.routers.ai.uuid.uuid4", return_value="task-123"),
            patch("app.routers.ai.cache.set", new_callable=AsyncMock, return_value=True) as mock_cache_set,
            patch("app.routers.ai._run_analyze_dividend_event_task", new_callable=AsyncMock) as mock_run_task,
        ):
            resp = client.get(
                "/ai/analyze_dividend_event_async",
                params={
                    "symbol": "ASX:CBA",
                    "ex_date": "2025-08-15",
                    "div_amount": 2.5,
                    "intent": "Capture income",
                },
            )

        assert resp.status_code == 202
        assert resp.json() == {
            "status": 202,
            "message": "Task started",
            "extra": {"task_id": "task-123", "state": async_task.TASK_STATE_RUNNING},
        }
        mock_cache_set.assert_awaited_once_with(
            "task-123",
            {"task_type": "analyze_dividend_event", "state": async_task.TASK_STATE_RUNNING},
            ttl=3600,
        )
        mock_run_task.assert_awaited_once_with(
            "task-123",
            "ASX:CBA",
            "2025-08-15",
            2.5,
            "Capture income",
        )

    def test_requires_inputs_when_starting_task(self):
        resp = client.get("/ai/analyze_dividend_event_async")

        assert resp.status_code == 400
        assert resp.json() == {
            "status": 400,
            "message": "Symbol, ex_date and div_amount are required when starting a task",
        }

    def test_poll_returns_running_status(self):
        task_entry = {"task_type": "analyze_dividend_event", "state": async_task.TASK_STATE_RUNNING}
        with patch("app.routers.ai.cache.get", new_callable=AsyncMock, return_value=task_entry) as mock_cache_get:
            resp = client.get("/ai/analyze_dividend_event_async", params={"task_id": "task-123"})

        assert resp.status_code == 202
        assert resp.json()["message"] == "Task is running"
        assert resp.json()["extra"] == {"task_id": "task-123", "state": async_task.TASK_STATE_RUNNING}
        mock_cache_get.assert_awaited_once_with("task-123")

    def test_poll_returns_404_for_missing_task(self):
        with patch("app.routers.ai.cache.get", new_callable=AsyncMock, return_value=None):
            resp = client.get("/ai/analyze_dividend_event_async", params={"task_id": "missing"})

        assert resp.status_code == 404
        assert resp.json() == {"status": 404, "message": "Task not found"}

    def test_poll_returns_completed_result(self):
        task_entry = {
            "task_type": "analyze_dividend_event",
            "state": async_task.TASK_STATE_COMPLETED,
            "result": {
                "status": 200,
                "message": "ok",
                "data": {
                    "symbol": "CBA.AX",
                    "price": 120.0,
                    "div_amount": 2.5,
                },
            },
        }
        with patch("app.routers.ai.cache.get", new_callable=AsyncMock, return_value=task_entry):
            resp = client.get("/ai/analyze_dividend_event_async", params={"task_id": "task-123"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == 200
        assert body["data"]["symbol"] == "CBA.AX"
        assert body["data"]["div_amount"] == 2.5
        assert body["extra"] == {"task_id": "task-123", "state": async_task.TASK_STATE_COMPLETED}

    def test_poll_returns_failed_status(self):
        task_entry = {
            "task_type": "analyze_dividend_event",
            "state": async_task.TASK_STATE_FAILED,
            "message": "Task failed",
        }
        with patch("app.routers.ai.cache.get", new_callable=AsyncMock, return_value=task_entry):
            resp = client.get("/ai/analyze_dividend_event_async", params={"task_id": "task-123"})

        assert resp.status_code == 500
        assert resp.json() == {
            "status": 500,
            "message": "Task failed",
            "extra": {"task_id": "task-123", "state": async_task.TASK_STATE_FAILED},
        }

    def test_background_task_caches_result(self):
        from app.routers import ai
        from app.schemas import ai as schemas_ai

        result = schemas_ai.AnalyzeDividendEventResponse(
            status=200,
            message="ok",
            data=DividendEventAnalysis(symbol="CBA.AX", price=120.0, div_amount=2.5),
        )
        with (
            patch(
                "app.routers.ai._get_analyze_dividend_event_result",
                new_callable=AsyncMock,
                return_value=result,
            ),
            patch("app.routers.ai.cache.set", new_callable=AsyncMock, return_value=True) as mock_cache_set,
        ):
            asyncio.run(
                ai._run_analyze_dividend_event_task(
                    "task-123",
                    "ASX:CBA",
                    "2025-08-15",
                    2.5,
                    "Capture income",
                )
            )

        mock_cache_set.assert_awaited_once_with(
            "task-123",
            {
                "task_type": "analyze_dividend_event",
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
                "app.routers.ai._get_analyze_dividend_event_result",
                new_callable=AsyncMock,
                side_effect=RuntimeError("LLM unavailable"),
            ),
            patch("app.routers.ai.cache.set", new_callable=AsyncMock, return_value=True) as mock_cache_set,
        ):
            asyncio.run(
                ai._run_analyze_dividend_event_task(
                    "task-123",
                    "ASX:CBA",
                    "2025-08-15",
                    2.5,
                    "Capture income",
                )
            )

        mock_cache_set.assert_awaited_once_with(
            "task-123",
            {
                "task_type": "analyze_dividend_event",
                "state": async_task.TASK_STATE_FAILED,
                "message": "Task failed",
            },
            ttl=3600,
        )


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
            patch("app.routers.ai.uuid.uuid4", return_value="task-456"),
            patch("app.routers.ai.cache.set", new_callable=AsyncMock, return_value=True) as mock_cache_set,
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
        with patch("app.routers.ai.cache.get", new_callable=AsyncMock, return_value=task_entry) as mock_cache_get:
            resp = client.post("/ai/analyze_ticker_async", params={"task_id": "task-456"})

        assert resp.status_code == 202
        assert resp.json()["message"] == "Task is running"
        assert resp.json()["extra"] == {"task_id": "task-456", "state": async_task.TASK_STATE_RUNNING}
        mock_cache_get.assert_awaited_once_with("task-456")

    def test_poll_returns_404_for_missing_task(self):
        with patch("app.routers.ai.cache.get", new_callable=AsyncMock, return_value=None):
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
        with patch("app.routers.ai.cache.get", new_callable=AsyncMock, return_value=task_entry):
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
        with patch("app.routers.ai.cache.get", new_callable=AsyncMock, return_value=task_entry):
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
            patch("app.routers.ai.cache.set", new_callable=AsyncMock, return_value=True) as mock_cache_set,
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
            patch("app.routers.ai.cache.set", new_callable=AsyncMock, return_value=True) as mock_cache_set,
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

    @patch(
        "app.routers.ai.service_build_portfolio.ai_build_portfolio",
        new_callable=AsyncMock,
    )
    def test_success(self, mock_build):
        mock_build.return_value = AnalyzePortfolioResult(llm_error=False, analysis="Portfolio: ...")
        resp = client.post("/ai/build_portfolio", json={"country": "AU"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == 200
        assert body["data"]["analysis"] == "Portfolio: ..."

    @patch(
        "app.routers.ai.service_build_portfolio.ai_build_portfolio",
        new_callable=AsyncMock,
    )
    def test_returns_400_when_service_returns_none(self, mock_build):
        mock_build.return_value = None
        resp = client.post("/ai/build_portfolio", json={"country": "AU"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == 400

    @patch(
        "app.routers.ai.service_build_portfolio.ai_build_portfolio",
        new_callable=AsyncMock,
    )
    def test_passes_existing_positions(self, mock_build):
        mock_build.return_value = AnalyzePortfolioResult(llm_error=False, analysis="result")
        positions = [{"ticker": "AAPL", "num_shares": 10, "market_price": 150.0}]
        resp = client.post(
            "/ai/build_portfolio",
            json={"country": "US", "current_allocation": positions},
        )
        assert resp.status_code == 200
        call_kwargs = mock_build.call_args.kwargs
        assert len(call_kwargs["existing_positions"]) == 1
        assert call_kwargs["existing_positions"][0].ticker == "AAPL"


# ===========================================================================
# POST /ai/build_portfolio_async
# ===========================================================================


class TestBuildPortfolioAsync:
    """Tests for POST /ai/build_portfolio_async endpoint."""

    def test_starts_task(self):
        with (
            patch("app.routers.ai.uuid.uuid4", return_value="task-789"),
            patch("app.routers.ai.cache.set", new_callable=AsyncMock, return_value=True) as mock_cache_set,
            patch("app.routers.ai._run_build_portfolio_task", new_callable=AsyncMock) as mock_run_task,
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

    def test_poll_returns_running_status(self):
        task_entry = {"task_type": "build_portfolio", "state": async_task.TASK_STATE_RUNNING}
        with patch("app.routers.ai.cache.get", new_callable=AsyncMock, return_value=task_entry) as mock_cache_get:
            resp = client.post("/ai/build_portfolio_async", params={"task_id": "task-789"})

        assert resp.status_code == 202
        assert resp.json()["message"] == "Task is running"
        assert resp.json()["extra"] == {"task_id": "task-789", "state": async_task.TASK_STATE_RUNNING}
        mock_cache_get.assert_awaited_once_with("task-789")

    def test_poll_returns_404_for_missing_task(self):
        with patch("app.routers.ai.cache.get", new_callable=AsyncMock, return_value=None):
            resp = client.post("/ai/build_portfolio_async", params={"task_id": "missing"})

        assert resp.status_code == 404
        assert resp.json() == {"status": 404, "message": "Task not found"}

    def test_poll_returns_completed_result(self):
        task_entry = {
            "task_type": "build_portfolio",
            "state": async_task.TASK_STATE_COMPLETED,
            "result": {
                "status": 200,
                "message": "ok",
                "data": {
                    "llm_error": False,
                    "analysis": "Recommended portfolio",
                    "rebalance_plan": "",
                },
            },
        }
        with patch("app.routers.ai.cache.get", new_callable=AsyncMock, return_value=task_entry):
            resp = client.post("/ai/build_portfolio_async", params={"task_id": "task-789"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == 200
        assert body["data"]["analysis"] == "Recommended portfolio"
        assert body["extra"] == {"task_id": "task-789", "state": async_task.TASK_STATE_COMPLETED}

    def test_poll_returns_failed_status(self):
        task_entry = {
            "task_type": "build_portfolio",
            "state": async_task.TASK_STATE_FAILED,
            "message": "Task failed",
        }
        with patch("app.routers.ai.cache.get", new_callable=AsyncMock, return_value=task_entry):
            resp = client.post("/ai/build_portfolio_async", params={"task_id": "task-789"})

        assert resp.status_code == 500
        assert resp.json() == {
            "status": 500,
            "message": "Task failed",
            "extra": {"task_id": "task-789", "state": async_task.TASK_STATE_FAILED},
        }

    def test_background_task_caches_result(self):
        from app.routers import ai
        from app.schemas import ai as schemas_ai

        req = schemas_ai.AnalyzePortfolioRequest(country="AU", investor_theme="Growth focused")
        result = schemas_ai.ReviewPortfolioResponse(
            status=200,
            message="ok",
            data=AnalyzePortfolioResult(llm_error=False, analysis="Recommended portfolio"),
        )
        with (
            patch(
                "app.routers.ai._get_build_portfolio_result",
                new_callable=AsyncMock,
                return_value=result,
            ),
            patch("app.routers.ai.cache.set", new_callable=AsyncMock, return_value=True) as mock_cache_set,
        ):
            asyncio.run(ai._run_build_portfolio_task("task-789", req))

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
        from app.routers import ai
        from app.schemas import ai as schemas_ai

        req = schemas_ai.AnalyzePortfolioRequest(country="AU")
        with (
            patch(
                "app.routers.ai._get_build_portfolio_result",
                new_callable=AsyncMock,
                side_effect=RuntimeError("LLM unavailable"),
            ),
            patch("app.routers.ai.cache.set", new_callable=AsyncMock, return_value=True) as mock_cache_set,
        ):
            asyncio.run(ai._run_build_portfolio_task("task-789", req))

        mock_cache_set.assert_awaited_once_with(
            "task-789",
            {
                "task_type": "build_portfolio",
                "state": async_task.TASK_STATE_FAILED,
                "message": "Task failed",
            },
            ttl=3600,
        )


# ===========================================================================
# POST /ai/analyze_portfolio
# ===========================================================================


class TestSpotlightPortfolio:
    """Tests for POST /ai/spotlight_portfolio endpoint."""

    @patch(
        "app.routers.ai.service_spotlight_portfolio.ai_spotlight_portfolio",
        new_callable=AsyncMock,
    )
    def test_success(self, mock_spotlight):
        mock_spotlight.return_value = AnalysisResult(llm_error=False, analysis="Immediate risks and actions")

        resp = client.post(
            "/ai/spotlight_portfolio",
            json={
                "country": "AU",
                "current_allocation": [{"ticker": "CBA.AX", "num_shares": 100, "market_price": 120.0}],
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == 200
        assert body["data"]["analysis"] == "Immediate risks and actions"
        mock_spotlight.assert_called_once()


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
        mock_build.return_value = AnalyzePortfolioResult(llm_error=False, analysis="New portfolio")
        resp = client.post(
            "/ai/analyze_portfolio",
            json={"country": "US", "current_allocation": []},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["analysis"] == "New portfolio"
        mock_build.assert_called_once()

    @patch(
        "app.routers.ai.service_build_portfolio.ai_build_portfolio",
        new_callable=AsyncMock,
    )
    def test_returns_400_when_service_fails(self, mock_build):
        mock_build.return_value = None
        resp = client.post(
            "/ai/analyze_portfolio",
            json={"country": "AU"},
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
