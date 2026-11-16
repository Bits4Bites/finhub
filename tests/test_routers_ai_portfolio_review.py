"""Black-box tests for portfolio construction-or-review routes."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import config
from app.main import app
from app.routers import async_task as router_async_task
from app.schemas import async_task
from app.services import msai_build_portfolio, msai_review_portfolio, portfolio_verification
from tests import portfolio_construction_fixtures, portfolio_review_fixtures

client = TestClient(app)


class _MemoryTaskCache:
    def __init__(self) -> None:
        self._entries: dict[str, object] = {}

    async def get(self, key: str) -> object | None:
        return self._entries.get(key)

    async def set(self, key: str, value: object, *, ttl: int | None = None) -> bool:
        self._entries[key] = value
        return True


@pytest.fixture
def isolated_task_cache(monkeypatch: pytest.MonkeyPatch) -> _MemoryTaskCache:
    task_cache = _MemoryTaskCache()
    monkeypatch.setattr(router_async_task.cache, "get", task_cache.get)
    monkeypatch.setattr(router_async_task.cache, "set", task_cache.set)
    return task_cache


def _holding_payload(index: int, *, positive: bool) -> dict[str, object]:
    return {
        "ticker": f"NASDAQ:T{index:02d}",
        "num_shares": 1 if positive else 0,
        "avg_price": 10,
        "market_price": 10,
    }


def _request_body(
    positions: list[dict[str, object]] | None = None,
    *,
    rebalance_plan: bool = False,
) -> dict[str, object]:
    return {
        "country": "US",
        "investor_theme": "Long-term quality growth",
        "rebalance_plan": rebalance_plan,
        "current_allocation": positions or [],
    }


class TestAnalyzePortfolioRouting:
    """Public contract for POST /ai/analyze_portfolio."""

    def test_redirects_through_ai_proxy_handler(self):
        with (
            patch.object(config.settings_finhub_proxy, "proxy_mode", "Redirect"),
            patch.object(config.settings_finhub_proxy, "url_ai_task_node", "https://proxy.example/finhub/"),
        ):
            response = client.post(
                "/ai/analyze_portfolio",
                json=_request_body(),
                follow_redirects=False,
            )

        assert response.status_code == 307
        assert response.headers["location"] == "https://proxy.example/finhub/ai/analyze_portfolio"

    @pytest.mark.parametrize(
        "positions",
        [
            [],
            [_holding_payload(index, positive=False) for index in range(3)],
            [_holding_payload(index, positive=index < 7) for index in range(20)],
        ],
        ids=["empty", "all-zero-nonempty", "exactly-thirty-five-percent-positive"],
    )
    def test_at_most_thirty_five_percent_positive_routes_to_construction(self, positions):
        with (
            patch(
                "app.routers.ai_portfolio_review.services_construction.ai_build_portfolio",
                new_callable=AsyncMock,
                return_value=portfolio_construction_fixtures.construction(),
            ),
            patch(
                "app.routers.ai_portfolio_review.services_review.ai_review_portfolio",
                new_callable=AsyncMock,
                return_value=portfolio_review_fixtures.review(),
            ),
        ):
            response = client.post("/ai/analyze_portfolio", json=_request_body(positions))

        assert response.status_code == 200
        assert response.json()["data"]["result_type"] == "PortfolioConstruction"

    def test_above_thirty_five_percent_positive_routes_to_review(self):
        positions = [_holding_payload(index, positive=index < 8) for index in range(20)]
        with (
            patch(
                "app.routers.ai_portfolio_review.services_construction.ai_build_portfolio",
                new_callable=AsyncMock,
                return_value=portfolio_construction_fixtures.construction(),
            ),
            patch(
                "app.routers.ai_portfolio_review.services_review.ai_review_portfolio",
                new_callable=AsyncMock,
                return_value=portfolio_review_fixtures.review(),
            ),
        ):
            response = client.post(
                "/ai/analyze_portfolio",
                json=_request_body(positions, rebalance_plan=True),
            )

        assert response.status_code == 200
        assert response.json()["data"]["result_type"] == "PortfolioReview"

    def test_investor_theme_is_required_for_every_branch(self):
        response = client.post(
            "/ai/analyze_portfolio",
            json={"country": "US", "current_allocation": []},
        )

        assert response.status_code == 422

    @pytest.mark.parametrize(
        ("error", "expected_status"),
        [
            (portfolio_verification.PortfolioInputError("invalid construction input"), 422),
            (portfolio_verification.PortfolioVerificationError("seed verification failed"), 502),
            (msai_build_portfolio.PortfolioConstructionAIError("construction failed"), 502),
        ],
        ids=["input", "market-verification", "ai-or-final-validation"],
    )
    def test_construction_branch_maps_errors(self, error, expected_status):
        positions = [_holding_payload(index, positive=False) for index in range(3)]
        with patch(
            "app.routers.ai_portfolio_review.services_construction.ai_build_portfolio",
            new_callable=AsyncMock,
            side_effect=error,
        ):
            response = client.post("/ai/analyze_portfolio", json=_request_body(positions))

        assert response.status_code == expected_status
        assert response.json()["status"] == expected_status

    @pytest.mark.parametrize(
        ("error", "expected_status"),
        [
            (portfolio_verification.PortfolioInputError("invalid review input"), 422),
            (portfolio_verification.PortfolioVerificationError("holding verification failed"), 502),
            (msai_review_portfolio.PortfolioReviewAIError("review failed"), 502),
        ],
        ids=["input", "market-verification", "ai-or-final-validation"],
    )
    def test_review_branch_maps_errors(self, error, expected_status):
        positions = [_holding_payload(0, positive=True)]
        with patch(
            "app.routers.ai_portfolio_review.services_review.ai_review_portfolio",
            new_callable=AsyncMock,
            side_effect=error,
        ):
            response = client.post("/ai/analyze_portfolio", json=_request_body(positions))

        assert response.status_code == expected_status
        assert response.json()["status"] == expected_status


class TestAnalyzePortfolioAsync:
    """Public contract for the asynchronous dispatch workflow."""

    def test_start_redirects_through_ai_proxy_handler(self):
        with (
            patch.object(config.settings_finhub_proxy, "proxy_mode", "Redirect"),
            patch.object(config.settings_finhub_proxy, "url_ai_task_node", "https://proxy.example/finhub/"),
        ):
            response = client.post(
                "/ai/start_analyze_portfolio_async",
                json=_request_body([_holding_payload(0, positive=True)]),
                follow_redirects=False,
            )

        assert response.status_code == 307
        assert response.headers["location"] == "https://proxy.example/finhub/ai/start_analyze_portfolio_async"

    def test_poll_redirects_through_ai_proxy_handler(self):
        with (
            patch.object(config.settings_finhub_proxy, "proxy_mode", "Redirect"),
            patch.object(config.settings_finhub_proxy, "url_ai_task_node", "https://proxy.example/finhub/"),
        ):
            response = client.post(
                "/ai/poll_analyze_portfolio_async",
                params={"task_id": "opaque-task"},
                follow_redirects=False,
            )

        assert response.status_code == 307
        assert (
            response.headers["location"]
            == "https://proxy.example/finhub/ai/poll_analyze_portfolio_async?task_id=opaque-task"
        )

    def test_start_body_is_required_in_openapi_and_at_runtime(self):
        operation = client.get("/openapi.json").json()["paths"]["/ai/start_analyze_portfolio_async"]["post"]

        assert operation["requestBody"]["required"] is True
        assert {"400", "422"} <= set(operation["responses"])
        missing_response = client.post("/ai/start_analyze_portfolio_async")
        invalid_response = client.post("/ai/start_analyze_portfolio_async", json={})
        assert missing_response.status_code == 400
        assert missing_response.json()["status"] == 400
        assert invalid_response.status_code == 422

    def test_start_to_poll_completed_review_and_duplicate_completed_start(self, isolated_task_cache):
        body = _request_body([_holding_payload(0, positive=True)])
        with patch(
            "app.routers.ai_portfolio_review.services_review.ai_review_portfolio",
            new_callable=AsyncMock,
            return_value=portfolio_review_fixtures.review(),
        ):
            started = client.post("/ai/start_analyze_portfolio_async", json=body)
            task_id = started.json()["extra"]["task_id"]
            polled = client.post(
                "/ai/poll_analyze_portfolio_async",
                params={"task_id": task_id},
            )
            duplicate = client.post("/ai/start_analyze_portfolio_async", json=body)

        assert started.status_code == 202
        assert polled.status_code == 200
        assert polled.json()["data"]["result_type"] == "PortfolioReview"
        assert polled.json()["extra"]["state"] == async_task.TASK_STATE_COMPLETED
        assert duplicate.status_code == 200
        assert duplicate.json()["extra"]["task_id"] == task_id
        assert duplicate.json()["data"]["result_type"] == "PortfolioReview"

    def test_poll_returns_completed_construction(self, isolated_task_cache):
        body = _request_body([_holding_payload(index, positive=False) for index in range(3)])
        with patch(
            "app.routers.ai_portfolio_review.services_construction.ai_build_portfolio",
            new_callable=AsyncMock,
            return_value=portfolio_construction_fixtures.construction(),
        ):
            started = client.post("/ai/start_analyze_portfolio_async", json=body)
            polled = client.post(
                "/ai/poll_analyze_portfolio_async",
                params={"task_id": started.json()["extra"]["task_id"]},
            )

        assert started.status_code == 202
        assert polled.status_code == 200
        assert polled.json()["data"]["result_type"] == "PortfolioConstruction"
        assert polled.json()["extra"]["state"] == async_task.TASK_STATE_COMPLETED

    @pytest.mark.parametrize(
        ("error", "expected_status"),
        [
            (portfolio_verification.PortfolioInputError("invalid review input"), 422),
            (portfolio_verification.PortfolioVerificationError("holding verification failed"), 502),
            (msai_review_portfolio.PortfolioReviewAIError("review failed"), 502),
            (RuntimeError("unexpected failure"), 500),
        ],
        ids=["input", "market-verification", "ai-or-final-validation", "unexpected"],
    )
    def test_start_to_poll_failure_and_duplicate_failed_start(
        self,
        isolated_task_cache,
        error,
        expected_status,
    ):
        body = _request_body([_holding_payload(0, positive=True)])
        with patch(
            "app.routers.ai_portfolio_review.services_review.ai_review_portfolio",
            new_callable=AsyncMock,
            side_effect=error,
        ):
            started = client.post("/ai/start_analyze_portfolio_async", json=body)
            task_id = started.json()["extra"]["task_id"]
            polled = client.post(
                "/ai/poll_analyze_portfolio_async",
                params={"task_id": task_id},
            )
            duplicate = client.post("/ai/start_analyze_portfolio_async", json=body)

        assert started.status_code == 202
        assert polled.status_code == expected_status
        assert polled.json()["extra"]["state"] == async_task.TASK_STATE_FAILED
        assert duplicate.status_code == expected_status
        assert duplicate.json()["extra"]["task_id"] == task_id
        assert duplicate.json()["extra"]["state"] == async_task.TASK_STATE_FAILED

    def test_duplicate_running_start_returns_existing_task_state(self):
        task_entry = SimpleNamespace(
            state=async_task.TASK_STATE_RUNNING,
            status=None,
            message=None,
            result=None,
        )
        with (
            patch.object(
                router_async_task,
                "start_task",
                new_callable=AsyncMock,
                return_value=("opaque-task", False),
            ),
            patch.object(
                router_async_task,
                "load_task",
                new_callable=AsyncMock,
                return_value=task_entry,
            ),
        ):
            response = client.post(
                "/ai/start_analyze_portfolio_async",
                json=_request_body([_holding_payload(0, positive=True)]),
            )

        assert response.status_code == 202
        assert response.json()["extra"] == {
            "task_id": "opaque-task",
            "state": async_task.TASK_STATE_RUNNING,
        }

    def test_poll_returns_running_state(self):
        task_entry = SimpleNamespace(
            state=async_task.TASK_STATE_RUNNING,
            status=None,
            message=None,
            result=None,
        )
        with patch.object(
            router_async_task,
            "load_task",
            new_callable=AsyncMock,
            return_value=task_entry,
        ):
            response = client.post(
                "/ai/poll_analyze_portfolio_async",
                params={"task_id": "opaque-task"},
            )

        assert response.status_code == 202
        assert response.json()["extra"]["state"] == async_task.TASK_STATE_RUNNING

    def test_poll_returns_404_for_unknown_task(self, isolated_task_cache):
        response = client.post(
            "/ai/poll_analyze_portfolio_async",
            params={"task_id": "unknown-task"},
        )

        assert response.status_code == 404
        assert response.json()["status"] == 404

    def test_poll_returns_500_for_invalid_task_state(self):
        with patch.object(
            router_async_task,
            "load_task",
            new_callable=AsyncMock,
            side_effect=HTTPException(status_code=500, detail="invalid retained state"),
        ):
            response = client.post(
                "/ai/poll_analyze_portfolio_async",
                params={"task_id": "opaque-task"},
            )

        assert response.status_code == 500
        assert response.json()["status"] == 500
