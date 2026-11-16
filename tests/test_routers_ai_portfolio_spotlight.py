from unittest import mock

import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app
from app.models import ai_portfolio_spotlight as models_spotlight
from app.services import msai_spotlight_portfolio as services_spotlight
from app.services import portfolio_verification
from tests import portfolio_spotlight_fixtures

client = TestClient(app)


@pytest.fixture(autouse=True)
def disable_ai_proxy(monkeypatch):
    monkeypatch.setattr(config.settings_finhub_proxy, "proxy_mode", "None")
    monkeypatch.setattr(config.settings_finhub_proxy, "url_ai_task_node", "")


def _request_body() -> dict[str, object]:
    return {
        "country": "US",
        "investor_theme": "Growth with moderate risk.",
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


async def _spotlight(**kwargs):
    return portfolio_spotlight_fixtures.analysis()


def test_spotlight_returns_contract_consistent_verified_snapshot_and_risk_actions():
    with mock.patch(
        "app.routers.ai_portfolio_spotlight.services_spotlight.ai_spotlight_portfolio",
        new=_spotlight,
    ):
        response = client.post("/ai/spotlight_portfolio", json=_request_body())

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["portfolio_empty"] is False
    assert data["rebalance_recommended"] == "YES"
    assert data["snapshot"]["country"] == "US"
    assert data["snapshot"]["currency"] == "USD"
    assert data["snapshot"]["total_market_value"] == 2000.0
    assert data["snapshot"]["holdings"] == [
        {
            "ticker": "NASDAQ:AAPL",
            "company_name": "Apple Inc.",
            "exchange": "NASDAQ",
            "currency": "USD",
            "num_shares": 10.0,
            "avg_price": 150.0,
            "market_price": 200.0,
            "price_source": "MarketData",
            "market_value": 2000.0,
            "current_allocation": 1.0,
            "target_allocation": 0.6,
            "allocation_drift": 0.4,
            "unrealized_profit_loss": 500.0,
            "tags": "growth",
        }
    ]
    assert data["risks"][0]["affected_tickers"] == ["NASDAQ:AAPL"]


def test_spotlight_returns_no_rebalance_when_no_material_risk_action_requires_it():
    async def no_material_risks(**kwargs):
        analysis_data = portfolio_spotlight_fixtures.analysis().model_dump(mode="python")
        analysis_data.update(
            {
                "risks": [],
                "rebalance_recommended": "NO",
                "references": [],
            }
        )
        return models_spotlight.PortfolioSpotlightAnalysis.model_validate(analysis_data)

    with mock.patch(
        "app.routers.ai_portfolio_spotlight.services_spotlight.ai_spotlight_portfolio",
        new=no_material_risks,
    ):
        response = client.post("/ai/spotlight_portfolio", json=_request_body())

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["portfolio_empty"] is False
    assert data["risks"] == []
    assert data["rebalance_recommended"] == "NO"
    assert data["references"] == []


@pytest.mark.parametrize(
    "body",
    [
        {
            "country": "US",
            "investor_theme": "Growth.",
            "current_allocation": [],
        },
        {
            "country": "US",
            "investor_theme": "Growth.",
            "current_allocation": [{"ticker": "NASDAQ:AAPL", "num_shares": 0}],
        },
        {
            "country": "US",
            "investor_theme": "   ",
            "current_allocation": [{"ticker": "NASDAQ:AAPL", "num_shares": 1}],
        },
        {
            "country": "US",
            "investor_theme": "Growth.",
            "current_allocation": [
                {"ticker": "NASDAQ:AAPL", "num_shares": 1},
                {"ticker": "nasdaq:aapl", "num_shares": 2},
            ],
        },
        {**_request_body(), "rebalance_plan": True},
        {**_request_body(), "country": "U" * 65},
    ],
)
def test_spotlight_request_rejects_invalid_or_removed_inputs(body):
    response = client.post("/ai/spotlight_portfolio", json=body)

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (portfolio_verification.PortfolioInputError("invalid portfolio"), 422),
        (portfolio_verification.PortfolioVerificationError("verification unavailable"), 502),
        (services_spotlight.PortfolioSpotlightAIError("spotlight unavailable"), 502),
    ],
)
def test_spotlight_maps_documented_service_failures(error, expected_status):
    async def fail(**kwargs):
        raise error

    with mock.patch(
        "app.routers.ai_portfolio_spotlight.services_spotlight.ai_spotlight_portfolio",
        new=fail,
    ):
        response = client.post("/ai/spotlight_portfolio", json=_request_body())

    assert response.status_code == expected_status
    assert response.json()["status"] == expected_status
    assert "data" not in response.json()


def test_async_spotlight_lifecycle_returns_running_then_completed_snapshot(deferred_task_store):
    with mock.patch(
        "app.routers.ai_portfolio_spotlight.services_spotlight.ai_spotlight_portfolio",
        new=_spotlight,
    ):
        started = client.post(
            "/ai/start_spotlight_portfolio_async",
            json=_request_body(),
        )
        task_id = started.json()["extra"]["task_id"]
        running = client.post(
            "/ai/poll_spotlight_portfolio_async",
            params={"task_id": task_id},
        )

        deferred_task_store.release()

        completed = client.post(
            "/ai/poll_spotlight_portfolio_async",
            params={"task_id": task_id},
        )
        duplicate = client.post(
            "/ai/start_spotlight_portfolio_async",
            json=_request_body(),
        )

    assert started.status_code == 202
    assert running.status_code == 202
    assert completed.status_code == 200
    assert completed.json()["extra"] == {"task_id": task_id, "state": "COMPLETED"}
    assert completed.json()["data"]["snapshot"]["holdings"][0]["ticker"] == "NASDAQ:AAPL"
    assert duplicate.json() == completed.json()


def test_async_spotlight_start_distinguishes_missing_and_invalid_bodies():
    missing = client.post("/ai/start_spotlight_portfolio_async")
    invalid = client.post("/ai/start_spotlight_portfolio_async", json={})

    assert missing.status_code == 400
    assert missing.json()["status"] == 400
    assert invalid.status_code == 422
    assert isinstance(invalid.json()["detail"], list)


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (portfolio_verification.PortfolioInputError("invalid portfolio"), 422),
        (portfolio_verification.PortfolioVerificationError("verification unavailable"), 502),
        (services_spotlight.PortfolioSpotlightAIError("spotlight unavailable"), 502),
        (RuntimeError("unexpected failure"), 500),
    ],
)
def test_async_spotlight_failures_are_pollable_and_reused(
    deferred_task_store,
    error,
    expected_status,
):
    async def fail(**kwargs):
        raise error

    with mock.patch(
        "app.routers.ai_portfolio_spotlight.services_spotlight.ai_spotlight_portfolio",
        new=fail,
    ):
        started = client.post(
            "/ai/start_spotlight_portfolio_async",
            json=_request_body(),
        )
        task_id = started.json()["extra"]["task_id"]
        deferred_task_store.release()
        failed = client.post(
            "/ai/poll_spotlight_portfolio_async",
            params={"task_id": task_id},
        )
        duplicate = client.post(
            "/ai/start_spotlight_portfolio_async",
            json=_request_body(),
        )

    assert failed.status_code == expected_status
    assert failed.json()["extra"] == {"task_id": task_id, "state": "FAILED"}
    assert duplicate.status_code == expected_status
    assert duplicate.json()["extra"] == {"task_id": task_id, "state": "FAILED"}
