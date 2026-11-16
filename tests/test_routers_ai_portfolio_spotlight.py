"""Black-box tests for portfolio-spotlight routes."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import config
from app.main import app
from app.routers import async_task as router_async_task
from app.schemas import async_task
from app.services import msai_spotlight_portfolio, portfolio_verification
from tests import portfolio_spotlight_fixtures

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


class TestPortfolioSpotlight:
    """Public contract for POST /ai/spotlight_portfolio."""

    def test_redirects_through_ai_proxy_handler(self):
        with (
            patch.object(config.settings_finhub_proxy, "proxy_mode", "Redirect"),
            patch.object(config.settings_finhub_proxy, "url_ai_task_node", "https://proxy.example/finhub/"),
        ):
            response = client.post(
                "/ai/spotlight_portfolio",
                json=_request_body(),
                follow_redirects=False,
            )

        assert response.status_code == 307
        assert response.headers["location"] == "https://proxy.example/finhub/ai/spotlight_portfolio"

    def test_returns_structured_spotlight_analysis(self):
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

    @pytest.mark.parametrize("portfolio_case", ["missing", "empty", "zero-share"])
    def test_rejects_portfolio_without_positive_share_positions(self, portfolio_case):
        request = _request_body()
        if portfolio_case == "missing":
            request.pop("current_allocation")
        elif portfolio_case == "empty":
            request["current_allocation"] = []
        else:
            request["current_allocation"][0]["num_shares"] = 0

        response = client.post("/ai/spotlight_portfolio", json=request)

        assert response.status_code == 422

    @pytest.mark.parametrize(
        ("include_theme", "investor_theme"),
        [
            (False, None),
            (True, None),
            (True, ""),
            (True, "   "),
        ],
    )
    def test_rejects_missing_null_or_blank_investor_theme(self, include_theme, investor_theme):
        request = _request_body()
        if not include_theme:
            request.pop("investor_theme")
        else:
            request["investor_theme"] = investor_theme

        response = client.post("/ai/spotlight_portfolio", json=request)

        assert response.status_code == 422

    def test_rejects_duplicate_normalized_tickers(self):
        request = _request_body()
        duplicate = request["current_allocation"][0].copy()
        duplicate["ticker"] = "nasdaq:aapl"
        request["current_allocation"].append(duplicate)

        response = client.post("/ai/spotlight_portfolio", json=request)

        assert response.status_code == 422

    def test_rejects_overlong_country_and_ticker(self):
        country_request = _request_body()
        country_request["country"] = "A" * 65
        ticker_request = _request_body()
        ticker_request["current_allocation"][0]["ticker"] = "A" * 33

        assert client.post("/ai/spotlight_portfolio", json=country_request).status_code == 422
        assert client.post("/ai/spotlight_portfolio", json=ticker_request).status_code == 422

    def test_rejects_removed_rebalance_plan_input(self):
        request = _request_body()
        request["rebalance_plan"] = True

        response = client.post("/ai/spotlight_portfolio", json=request)

        assert response.status_code == 422

    @pytest.mark.parametrize(
        ("error", "expected_status"),
        [
            (portfolio_verification.PortfolioInputError("invalid portfolio"), 422),
            (portfolio_verification.PortfolioVerificationError("market data unavailable"), 502),
            (msai_spotlight_portfolio.PortfolioSpotlightAIError("provider or structured output failed"), 502),
        ],
        ids=["input", "market-verification", "provider-or-structured-output"],
    )
    def test_maps_service_failures(self, error, expected_status):
        with patch(
            "app.routers.ai_portfolio_spotlight.services_spotlight.ai_spotlight_portfolio",
            new_callable=AsyncMock,
            side_effect=error,
        ):
            response = client.post("/ai/spotlight_portfolio", json=_request_body())

        assert response.status_code == expected_status
        assert response.json()["status"] == expected_status

    def test_maps_provider_independent_final_validation_failure_to_502(self):
        with patch(
            "app.routers.ai_portfolio_spotlight.services_spotlight.ai_spotlight_portfolio",
            new_callable=AsyncMock,
            side_effect=msai_spotlight_portfolio.PortfolioSpotlightAIError(
                "Portfolio spotlight failed final validation"
            ),
        ):
            response = client.post("/ai/spotlight_portfolio", json=_request_body())

        assert response.status_code == 502
        assert response.json()["status"] == 502


class TestPortfolioSpotlightAsync:
    """Public contract for the asynchronous spotlight workflow."""

    def test_start_redirects_through_ai_proxy_handler(self):
        with (
            patch.object(config.settings_finhub_proxy, "proxy_mode", "Redirect"),
            patch.object(config.settings_finhub_proxy, "url_ai_task_node", "https://proxy.example/finhub/"),
        ):
            response = client.post(
                "/ai/start_spotlight_portfolio_async",
                json=_request_body(),
                follow_redirects=False,
            )

        assert response.status_code == 307
        assert response.headers["location"] == "https://proxy.example/finhub/ai/start_spotlight_portfolio_async"

    def test_poll_redirects_through_ai_proxy_handler(self):
        with (
            patch.object(config.settings_finhub_proxy, "proxy_mode", "Redirect"),
            patch.object(config.settings_finhub_proxy, "url_ai_task_node", "https://proxy.example/finhub/"),
        ):
            response = client.post(
                "/ai/poll_spotlight_portfolio_async",
                params={"task_id": "opaque-task"},
                follow_redirects=False,
            )

        assert response.status_code == 307
        assert (
            response.headers["location"]
            == "https://proxy.example/finhub/ai/poll_spotlight_portfolio_async?task_id=opaque-task"
        )

    def test_start_body_is_required_in_openapi_and_at_runtime(self):
        operation = client.get("/openapi.json").json()["paths"]["/ai/start_spotlight_portfolio_async"]["post"]

        assert operation["requestBody"]["required"] is True
        assert {"400", "422"} <= set(operation["responses"])
        missing_response = client.post("/ai/start_spotlight_portfolio_async")
        invalid_response = client.post("/ai/start_spotlight_portfolio_async", json={})
        assert missing_response.status_code == 400
        assert missing_response.json()["status"] == 400
        assert invalid_response.status_code == 422

    def test_start_to_poll_success_and_duplicate_completed_start(self, isolated_task_cache):
        with patch(
            "app.routers.ai_portfolio_spotlight.services_spotlight.ai_spotlight_portfolio",
            new_callable=AsyncMock,
            return_value=portfolio_spotlight_fixtures.analysis(),
        ):
            started = client.post("/ai/start_spotlight_portfolio_async", json=_request_body())
            task_id = started.json()["extra"]["task_id"]
            polled = client.post(
                "/ai/poll_spotlight_portfolio_async",
                params={"task_id": task_id},
            )
            duplicate = client.post("/ai/start_spotlight_portfolio_async", json=_request_body())

        assert started.status_code == 202
        assert started.json()["extra"]["state"] == async_task.TASK_STATE_RUNNING
        assert polled.status_code == 200
        assert polled.json()["data"]["rebalance_recommended"] == "YES"
        assert polled.json()["extra"]["state"] == async_task.TASK_STATE_COMPLETED
        assert duplicate.status_code == 200
        assert duplicate.json()["extra"]["task_id"] == task_id
        assert duplicate.json()["extra"]["state"] == async_task.TASK_STATE_COMPLETED

    @pytest.mark.parametrize(
        ("error", "expected_status"),
        [
            (portfolio_verification.PortfolioInputError("invalid portfolio"), 422),
            (portfolio_verification.PortfolioVerificationError("market data unavailable"), 502),
            (msai_spotlight_portfolio.PortfolioSpotlightAIError("spotlight failed"), 502),
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
        with patch(
            "app.routers.ai_portfolio_spotlight.services_spotlight.ai_spotlight_portfolio",
            new_callable=AsyncMock,
            side_effect=error,
        ):
            started = client.post("/ai/start_spotlight_portfolio_async", json=_request_body())
            task_id = started.json()["extra"]["task_id"]
            polled = client.post(
                "/ai/poll_spotlight_portfolio_async",
                params={"task_id": task_id},
            )
            duplicate = client.post("/ai/start_spotlight_portfolio_async", json=_request_body())

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
            response = client.post("/ai/start_spotlight_portfolio_async", json=_request_body())

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
                "/ai/poll_spotlight_portfolio_async",
                params={"task_id": "opaque-task"},
            )

        assert response.status_code == 202
        assert response.json()["extra"]["state"] == async_task.TASK_STATE_RUNNING

    def test_poll_returns_404_for_unknown_task(self, isolated_task_cache):
        response = client.post(
            "/ai/poll_spotlight_portfolio_async",
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
                "/ai/poll_spotlight_portfolio_async",
                params={"task_id": "opaque-task"},
            )

        assert response.status_code == 500
        assert response.json()["status"] == 500
