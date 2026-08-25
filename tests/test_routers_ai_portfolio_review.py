import asyncio
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app import config
from app.main import app
from app.schemas import ai_portfolio_review as schemas_review
from app.schemas import async_task
from app.services import msai_review_portfolio, portfolio_verification
from tests import portfolio_construction_fixtures, portfolio_review_fixtures

client = TestClient(app)


def _holding_payload(index: int, *, positive: bool) -> dict[str, object]:
    return {
        "ticker": f"NASDAQ:T{index:02d}",
        "num_shares": 1 if positive else 0,
        "avg_price": 10,
        "market_price": 10,
    }


class TestAnalyzePortfolioRouting:
    def test_redirects_through_ai_proxy_handler(self):
        with (
            patch.object(config.settings_finhub_proxy, "proxy_mode", "Redirect"),
            patch.object(config.settings_finhub_proxy, "url_ai_task_node", "https://proxy.example/finhub/"),
        ):
            response = client.post(
                "/ai/analyze_portfolio",
                json={
                    "country": "US",
                    "investor_theme": "Long-term quality growth",
                    "current_allocation": [],
                },
                follow_redirects=False,
            )

        assert response.status_code == 307
        assert response.headers["location"] == "https://proxy.example/finhub/ai/analyze_portfolio"

    @patch(
        "app.routers.ai_portfolio_review.services_construction.ai_build_portfolio",
        new_callable=AsyncMock,
        return_value=portfolio_construction_fixtures.construction(),
    )
    def test_empty_portfolio_routes_to_construction(self, mock_build):
        response = client.post(
            "/ai/analyze_portfolio",
            json={
                "country": "US",
                "investor_theme": "Long-term quality growth",
                "current_allocation": [],
            },
        )

        assert response.status_code == 200
        assert response.json()["data"]["result_type"] == "PortfolioConstruction"
        mock_build.assert_awaited_once()

    @patch(
        "app.routers.ai_portfolio_review.services_construction.ai_build_portfolio",
        new_callable=AsyncMock,
        return_value=portfolio_construction_fixtures.construction(),
    )
    def test_exactly_thirty_five_percent_positive_routes_to_construction(self, mock_build):
        positions = [_holding_payload(index, positive=index < 7) for index in range(20)]

        response = client.post(
            "/ai/analyze_portfolio",
            json={
                "country": "US",
                "investor_theme": "Long-term quality growth",
                "current_allocation": positions,
            },
        )

        assert response.status_code == 200
        assert len(mock_build.await_args.kwargs["portfolio"]) == 20

    @patch(
        "app.routers.ai_portfolio_review.services_review.ai_review_portfolio",
        new_callable=AsyncMock,
        return_value=portfolio_review_fixtures.review(),
    )
    def test_above_thirty_five_percent_routes_to_review(self, mock_review):
        positions = [_holding_payload(index, positive=index < 8) for index in range(20)]

        response = client.post(
            "/ai/analyze_portfolio",
            json={
                "country": "US",
                "investor_theme": "Long-term quality growth",
                "rebalance_plan": True,
                "current_allocation": positions,
            },
        )

        assert response.status_code == 200
        assert response.json()["data"]["result_type"] == "PortfolioReview"
        assert mock_review.await_args.kwargs["rebalance_plan"] is True

    def test_investor_theme_is_required_for_every_branch(self):
        response = client.post(
            "/ai/analyze_portfolio",
            json={"country": "US", "current_allocation": []},
        )

        assert response.status_code == 422

    @patch(
        "app.routers.ai_portfolio_review.services_review.ai_review_portfolio",
        new_callable=AsyncMock,
        side_effect=portfolio_verification.PortfolioInputError("Conflicting strategy"),
    )
    def test_invalid_review_input_returns_422(self, mock_review):
        response = client.post(
            "/ai/analyze_portfolio",
            json={
                "country": "US",
                "investor_theme": "Long-term and swing trading",
                "current_allocation": [_holding_payload(0, positive=True)],
            },
        )

        assert response.status_code == 422
        assert response.json()["message"] == "Conflicting strategy"

    @patch(
        "app.routers.ai_portfolio_review.services_review.ai_review_portfolio",
        new_callable=AsyncMock,
        side_effect=msai_review_portfolio.PortfolioReviewAIError("Structured output failed"),
    )
    def test_review_provider_failure_returns_502(self, mock_review):
        response = client.post(
            "/ai/analyze_portfolio",
            json={
                "country": "US",
                "investor_theme": "Long-term growth",
                "current_allocation": [_holding_payload(0, positive=True)],
            },
        )

        assert response.status_code == 502
        assert response.json()["message"] == "Structured output failed"


class TestAnalyzePortfolioAsync:
    def test_poll_redirects_through_ai_proxy_handler(self):
        with (
            patch.object(config.settings_finhub_proxy, "proxy_mode", "Redirect"),
            patch.object(config.settings_finhub_proxy, "url_ai_task_node", "https://proxy.example/finhub/"),
        ):
            response = client.post(
                "/ai/analyze_portfolio_async",
                params={"task_id": "task-review"},
                follow_redirects=False,
            )

        assert response.status_code == 307
        assert (
            response.headers["location"]
            == "https://proxy.example/finhub/ai/analyze_portfolio_async?task_id=task-review"
        )

    def test_starts_task(self):
        with (
            patch("app.routers.async_task._generate_task_id", return_value="task-review"),
            patch(
                "app.routers.async_task.cache.set",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_cache_set,
            patch(
                "app.routers.ai_portfolio_review._run_task",
                new_callable=AsyncMock,
            ) as mock_run_task,
        ):
            response = client.post(
                "/ai/analyze_portfolio_async",
                json={
                    "country": "US",
                    "investor_theme": "Long-term growth",
                    "current_allocation": [_holding_payload(0, positive=True)],
                },
            )

        assert response.status_code == 202
        assert response.json()["extra"] == {
            "task_id": "task-review",
            "state": async_task.TASK_STATE_RUNNING,
        }
        mock_cache_set.assert_awaited_once()
        mock_run_task.assert_awaited_once()

    def test_requires_body_when_starting_task(self):
        response = client.post("/ai/analyze_portfolio_async")

        assert response.status_code == 400
        assert response.json()["message"] == "Request body is required when starting a task"

    def test_poll_returns_completed_discriminated_review(self):
        result = schemas_review.AnalyzePortfolioResponse(
            status=200,
            message="ok",
            data=portfolio_review_fixtures.review(),
        )
        task_entry = {
            "task_type": "analyze_portfolio",
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
            response = client.post(
                "/ai/analyze_portfolio_async",
                params={"task_id": "task-review"},
            )

        assert response.status_code == 200
        assert response.json()["data"]["result_type"] == "PortfolioReview"
        assert response.json()["extra"]["state"] == async_task.TASK_STATE_COMPLETED

    def test_poll_preserves_background_failure_status(self):
        task_entry = {
            "task_type": "analyze_portfolio",
            "state": async_task.TASK_STATE_FAILED,
            "status": 502,
            "message": "Research failed",
        }
        with patch(
            "app.routers.async_task.cache.get",
            new_callable=AsyncMock,
            return_value=task_entry,
        ):
            response = client.post(
                "/ai/analyze_portfolio_async",
                params={"task_id": "task-review"},
            )

        assert response.status_code == 502
        assert response.json()["message"] == "Research failed"

    def test_background_task_stores_typed_result(self):
        from app.routers import ai_portfolio_review as router_review

        request = schemas_review.AnalyzePortfolioRequest(
            country="US",
            investor_theme="Long-term growth",
            current_allocation=portfolio_review_fixtures.holdings(),
        )
        result = schemas_review.AnalyzePortfolioResponse(
            status=200,
            message="ok",
            data=portfolio_review_fixtures.review(),
        )
        with (
            patch(
                "app.routers.ai_portfolio_review._analyze",
                new_callable=AsyncMock,
                return_value=result,
            ),
            patch(
                "app.routers.async_task.cache.set",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_cache_set,
        ):
            asyncio.run(router_review._run_task("task-review", request))

        stored = mock_cache_set.await_args.args[1]
        assert stored["state"] == async_task.TASK_STATE_COMPLETED
        assert stored["result"]["data"]["result_type"] == "PortfolioReview"
