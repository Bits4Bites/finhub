"""Black-box tests for AI vendor and portfolio-construction routes."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import config
from app.main import app
from app.routers import async_task as router_async_task
from app.schemas import async_task
from app.services import msai_build_portfolio as service_build_portfolio
from app.services import portfolio_verification
from tests import portfolio_construction_fixtures

client = TestClient(app)


class _MemoryTaskCache:
    def __init__(self) -> None:
        self._entries: dict[str, object] = {}

    async def get(self, key: str) -> object | None:
        return self._entries.get(key)

    async def set(self, key: str, value: object, *, ttl: int | None = None) -> bool:
        self._entries[key] = value
        return True

    def expire_all(self) -> None:
        self._entries.clear()


@pytest.fixture
def isolated_task_cache(monkeypatch: pytest.MonkeyPatch) -> _MemoryTaskCache:
    task_cache = _MemoryTaskCache()
    monkeypatch.setattr(router_async_task.cache, "get", task_cache.get)
    monkeypatch.setattr(router_async_task.cache, "set", task_cache.set)
    return task_cache


def _build_request() -> dict[str, object]:
    return {
        "country": "US",
        "investor_theme": "Durable growth with moderate risk.",
    }


class TestGetVendors:
    """Public contract for GET /ai/vendors."""

    def test_returns_normalized_isolated_configuration(self):
        primary = config.LLMConfig()
        primary.models = {"model-a", "model-b"}
        economy = config.LLMConfig()
        economy.models = {"model-lite"}

        with patch.object(
            config.settings_llm_vendor,
            "vendors",
            {
                "example_ai": {
                    "primary": primary,
                    "economy": economy,
                }
            },
        ):
            response = client.get("/ai/vendors")

        assert response.status_code == 200
        assert response.json()["status"] == 200
        assert response.json()["message"] == "ok"
        assert set(response.json()["data"]) == {"EXAMPLE_AI"}
        vendor = response.json()["data"]["EXAMPLE_AI"]
        assert vendor["name"] == "EXAMPLE_AI"
        assert set(vendor["tier_models"]) == {"PRIMARY", "ECONOMY"}
        assert set(vendor["tier_models"]["PRIMARY"]) == {"model-a", "model-b"}
        assert vendor["tier_models"]["ECONOMY"] == ["model-lite"]

    def test_returns_empty_data_when_no_vendors_are_enabled(self):
        with patch.object(config.settings_llm_vendor, "vendors", {}):
            response = client.get("/ai/vendors")

        assert response.status_code == 200
        assert response.json()["data"] == {}


class TestBuildPortfolio:
    """Public contract for POST /ai/build_portfolio."""

    def test_redirects_through_ai_proxy_handler(self):
        with (
            patch.object(config.settings_finhub_proxy, "proxy_mode", "Redirect"),
            patch.object(config.settings_finhub_proxy, "url_ai_task_node", "https://proxy.example/finhub/"),
        ):
            response = client.post(
                "/ai/build_portfolio",
                json=_build_request(),
                follow_redirects=False,
            )

        assert response.status_code == 307
        assert response.headers["location"] == "https://proxy.example/finhub/ai/build_portfolio"

    @patch(
        "app.routers.ai_portfolio_construction.service_build_portfolio.ai_build_portfolio",
        new_callable=AsyncMock,
    )
    def test_returns_scratch_construction(self, mock_build):
        mock_build.return_value = portfolio_construction_fixtures.construction()

        response = client.post("/ai/build_portfolio", json=_build_request())

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["result_type"] == "PortfolioConstruction"
        assert data["construction_mode"] == "Scratch"
        assert data["target_portfolio"][0]["allocation"] == 0.4
        assert "analysis" not in data
        assert "rebalance_plan" not in data

    @patch(
        "app.routers.ai_portfolio_construction.service_build_portfolio.ai_build_portfolio",
        new_callable=AsyncMock,
    )
    def test_preserves_unavailable_action_plan(self, mock_build):
        mock_build.return_value = portfolio_construction_fixtures.construction(action_plan_available=False)

        response = client.post("/ai/build_portfolio", json=_build_request())

        assert response.status_code == 200
        assert response.json()["data"]["action_plan"] is None

    @pytest.mark.parametrize(
        "body",
        [
            {},
            {"country": "US"},
            {"country": "US", "investor_theme": "   "},
            {
                "country": "US",
                "investor_theme": "Growth",
                "current_allocation": [
                    {"ticker": "aapl", "num_shares": 1},
                    {"ticker": "AAPL", "num_shares": 2},
                ],
            },
            {
                "country": "US",
                "investor_theme": "Growth",
                "rebalance_plan": True,
            },
        ],
    )
    def test_rejects_invalid_requests(self, body):
        response = client.post("/ai/build_portfolio", json=body)

        assert response.status_code == 422

    @pytest.mark.parametrize(
        ("error", "expected_status"),
        [
            (portfolio_verification.PortfolioInputError("invalid portfolio"), 422),
            (portfolio_verification.PortfolioVerificationError("market data unavailable"), 502),
            (service_build_portfolio.PortfolioConstructionAIError("construction failed"), 502),
        ],
        ids=["input", "market-verification", "ai-or-final-validation"],
    )
    def test_maps_service_failures(self, error, expected_status):
        with patch(
            "app.routers.ai_portfolio_construction.service_build_portfolio.ai_build_portfolio",
            new_callable=AsyncMock,
            side_effect=error,
        ):
            response = client.post("/ai/build_portfolio", json=_build_request())

        assert response.status_code == expected_status
        assert response.json()["status"] == expected_status
        assert "data" not in response.json()


class TestBuildPortfolioAsync:
    """Public contract for the asynchronous construction workflow."""

    def test_start_redirects_through_ai_proxy_handler(self):
        with (
            patch.object(config.settings_finhub_proxy, "proxy_mode", "Redirect"),
            patch.object(config.settings_finhub_proxy, "url_ai_task_node", "https://proxy.example/finhub/"),
        ):
            response = client.post(
                "/ai/start_build_portfolio_async",
                json=_build_request(),
                follow_redirects=False,
            )

        assert response.status_code == 307
        assert response.headers["location"] == "https://proxy.example/finhub/ai/start_build_portfolio_async"

    def test_poll_redirects_through_ai_proxy_handler(self):
        with (
            patch.object(config.settings_finhub_proxy, "proxy_mode", "Redirect"),
            patch.object(config.settings_finhub_proxy, "url_ai_task_node", "https://proxy.example/finhub/"),
        ):
            response = client.post(
                "/ai/poll_build_portfolio_async",
                params={"task_id": "opaque-task"},
                follow_redirects=False,
            )

        assert response.status_code == 307
        assert (
            response.headers["location"]
            == "https://proxy.example/finhub/ai/poll_build_portfolio_async?task_id=opaque-task"
        )

    def test_start_body_is_required_in_openapi_and_at_runtime(self):
        operation = client.get("/openapi.json").json()["paths"]["/ai/start_build_portfolio_async"]["post"]

        assert operation["requestBody"]["required"] is True
        assert {"400", "422"} <= set(operation["responses"])
        missing_response = client.post("/ai/start_build_portfolio_async")
        invalid_response = client.post("/ai/start_build_portfolio_async", json={})
        assert missing_response.status_code == 400
        assert missing_response.json()["status"] == 400
        assert invalid_response.status_code == 422

    def test_start_to_poll_success_and_duplicate_completed_start(self, isolated_task_cache):
        construction = portfolio_construction_fixtures.construction(action_plan_available=False)
        with patch(
            "app.routers.ai_portfolio_construction.service_build_portfolio.ai_build_portfolio",
            new_callable=AsyncMock,
            return_value=construction,
        ):
            started = client.post("/ai/start_build_portfolio_async", json=_build_request())
            task_id = started.json()["extra"]["task_id"]
            polled = client.post(
                "/ai/poll_build_portfolio_async",
                params={"task_id": task_id},
            )
            duplicate = client.post("/ai/start_build_portfolio_async", json=_build_request())

        assert started.status_code == 202
        assert started.json()["extra"]["state"] == async_task.TASK_STATE_RUNNING
        assert polled.status_code == 200
        assert polled.json()["extra"] == {
            "task_id": task_id,
            "state": async_task.TASK_STATE_COMPLETED,
        }
        assert polled.json()["data"]["action_plan"] is None
        assert duplicate.status_code == 200
        assert duplicate.json()["extra"]["task_id"] == task_id
        assert duplicate.json()["extra"]["state"] == async_task.TASK_STATE_COMPLETED

    @pytest.mark.parametrize(
        ("error", "expected_status"),
        [
            (portfolio_verification.PortfolioInputError("invalid portfolio"), 422),
            (portfolio_verification.PortfolioVerificationError("market data unavailable"), 502),
            (service_build_portfolio.PortfolioConstructionAIError("construction failed"), 502),
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
            "app.routers.ai_portfolio_construction.service_build_portfolio.ai_build_portfolio",
            new_callable=AsyncMock,
            side_effect=error,
        ):
            started = client.post("/ai/start_build_portfolio_async", json=_build_request())
            task_id = started.json()["extra"]["task_id"]
            polled = client.post(
                "/ai/poll_build_portfolio_async",
                params={"task_id": task_id},
            )
            duplicate = client.post("/ai/start_build_portfolio_async", json=_build_request())

        assert started.status_code == 202
        assert polled.status_code == expected_status
        assert polled.json()["status"] == expected_status
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
            response = client.post("/ai/start_build_portfolio_async", json=_build_request())

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
                "/ai/poll_build_portfolio_async",
                params={"task_id": "  opaque-task  "},
            )

        assert response.status_code == 202
        assert response.json()["extra"] == {
            "task_id": "opaque-task",
            "state": async_task.TASK_STATE_RUNNING,
        }

    def test_poll_returns_404_for_unknown_task(self, isolated_task_cache):
        response = client.post(
            "/ai/poll_build_portfolio_async",
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
                "/ai/poll_build_portfolio_async",
                params={"task_id": "opaque-task"},
            )

        assert response.status_code == 500
        assert response.json()["status"] == 500

    def test_expired_task_is_not_pollable_and_can_be_started_again(self, isolated_task_cache):
        construction = portfolio_construction_fixtures.construction()
        with patch(
            "app.routers.ai_portfolio_construction.service_build_portfolio.ai_build_portfolio",
            new_callable=AsyncMock,
            return_value=construction,
        ):
            started = client.post("/ai/start_build_portfolio_async", json=_build_request())
            task_id = started.json()["extra"]["task_id"]
            isolated_task_cache.expire_all()
            expired_poll = client.post(
                "/ai/poll_build_portfolio_async",
                params={"task_id": task_id},
            )
            restarted = client.post("/ai/start_build_portfolio_async", json=_build_request())

        assert expired_poll.status_code == 404
        assert restarted.status_code == 202
        assert restarted.json()["extra"]["state"] == async_task.TASK_STATE_RUNNING
