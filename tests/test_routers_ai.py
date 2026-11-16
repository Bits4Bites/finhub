from unittest import mock

import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app
from app.services import msai_build_portfolio as services_construction
from app.services import portfolio_verification
from tests import portfolio_construction_fixtures

client = TestClient(app)


@pytest.fixture(autouse=True)
def disable_ai_proxy(monkeypatch):
    monkeypatch.setattr(config.settings_finhub_proxy, "proxy_mode", "None")
    monkeypatch.setattr(config.settings_finhub_proxy, "url_ai_task_node", "")


def _build_request(*, seeded: bool = False, budget: bool = True) -> dict[str, object]:
    theme = "Durable growth with moderate risk."
    if budget:
        theme += " Total budget USD 1,000."
    body: dict[str, object] = {
        "country": "US",
        "investor_theme": theme,
    }
    if seeded:
        body["current_allocation"] = [
            {
                "ticker": "NASDAQ:AAPL",
                "num_shares": 10,
                "avg_price": 150,
            }
        ]
    return body


async def _construction_for_request(*, portfolio, country, investor_theme):
    positive_holding = any(holding.num_shares > 0 for holding in portfolio)
    mode = "Seeded" if positive_holding else "Scratch"
    action_plan_available = positive_holding or "budget" in investor_theme.casefold()
    result = portfolio_construction_fixtures.construction(
        mode=mode,
        action_plan_available=action_plan_available,
    )
    result_data = result.model_dump(mode="python")
    result_data.update(
        {
            "country": country,
            "investor_theme": investor_theme,
        }
    )
    return type(result).model_validate(result_data)


def test_vendors_returns_only_normalized_public_catalog_data(monkeypatch):
    primary = config.LLMConfig(
        vendor_name="Example AI",
        api_tier="Primary",
        api_key="must-not-leak",
        endpoint="https://private.invalid",
        models={"model-b", "model-a"},
    )
    monkeypatch.setattr(
        config.settings_llm_vendor,
        "vendors",
        {"example_ai": {"primary": primary}},
    )

    response = client.get("/ai/vendors")

    assert response.status_code == 200
    assert response.json()["status"] == 200
    assert response.json()["data"]["EXAMPLE_AI"]["name"] == "EXAMPLE_AI"
    assert set(response.json()["data"]["EXAMPLE_AI"]["tier_models"]["PRIMARY"]) == {
        "model-a",
        "model-b",
    }
    assert "must-not-leak" not in response.text
    assert "private.invalid" not in response.text


def test_vendors_returns_empty_data_for_an_empty_isolated_catalog(monkeypatch):
    monkeypatch.setattr(config.settings_llm_vendor, "vendors", {})

    response = client.get("/ai/vendors")

    assert response.status_code == 200
    assert response.json()["status"] == 200
    assert response.json()["data"] == {}


@pytest.mark.parametrize(
    ("body", "expected_mode", "expected_budget"),
    [
        (
            _build_request(seeded=False, budget=True),
            "Scratch",
            {
                "budget_type": "Total",
                "is_inferred": False,
                "amount": 1000.0,
                "currency": "USD",
            },
        ),
        (_build_request(seeded=False, budget=False), "Scratch", None),
        (
            _build_request(seeded=True, budget=False),
            "Seeded",
            {
                "budget_type": "Recurring",
                "is_inferred": True,
                "amount": 200.0,
                "currency": "USD",
            },
        ),
    ],
)
def test_build_portfolio_exposes_scratch_seeded_and_budget_outcomes(
    body,
    expected_mode,
    expected_budget,
):
    with mock.patch(
        "app.routers.ai_portfolio_construction.service_build_portfolio.ai_build_portfolio",
        new=_construction_for_request,
    ):
        response = client.post("/ai/build_portfolio", json=body)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["construction_mode"] == expected_mode
    assert data["country"] == "US"
    assert data["investor_theme"] == body["investor_theme"]
    if expected_budget is None:
        assert data["action_plan"] is None
    else:
        returned_budget = data["action_plan"]["budget"]
        for field, expected_value in expected_budget.items():
            assert returned_budget[field] == expected_value
    if expected_mode == "Scratch":
        assert data["verified_seed_holdings"] == []
    else:
        assert [holding["ticker"] for holding in data["verified_seed_holdings"]] == ["NASDAQ:AAPL"]


def test_build_portfolio_reports_conflicting_budget_input_as_unprocessable():
    async def reject_conflicting_budget(**kwargs):
        raise portfolio_verification.PortfolioInputError("conflicting budget input")

    body = _build_request()
    body["investor_theme"] = "Invest USD 1,000 total and contribute USD 200 monthly."
    with mock.patch(
        "app.routers.ai_portfolio_construction.service_build_portfolio.ai_build_portfolio",
        new=reject_conflicting_budget,
    ):
        response = client.post("/ai/build_portfolio", json=body)

    assert response.status_code == 422
    assert response.json()["status"] == 422
    assert "data" not in response.json()


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"country": "US", "investor_theme": "   "},
        {**_build_request(), "rebalance_plan": True},
        {
            **_build_request(),
            "current_allocation": [
                {"ticker": "NASDAQ:AAPL", "num_shares": 1},
                {"ticker": "nasdaq:aapl", "num_shares": 2},
            ],
        },
    ],
)
def test_build_portfolio_rejects_invalid_or_undocumented_request_shapes(body):
    response = client.post("/ai/build_portfolio", json=body)

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (portfolio_verification.PortfolioInputError("invalid portfolio"), 422),
        (portfolio_verification.PortfolioVerificationError("verification unavailable"), 502),
        (services_construction.PortfolioConstructionAIError("construction unavailable"), 502),
    ],
)
def test_build_portfolio_maps_documented_service_failures(error, expected_status):
    async def fail(**kwargs):
        raise error

    with mock.patch(
        "app.routers.ai_portfolio_construction.service_build_portfolio.ai_build_portfolio",
        new=fail,
    ):
        response = client.post("/ai/build_portfolio", json=_build_request())

    assert response.status_code == expected_status
    assert response.json()["status"] == expected_status
    assert "data" not in response.json()


def test_unexpected_build_failure_returns_public_500_envelope():
    async def fail(**kwargs):
        raise RuntimeError("unexpected failure")

    with mock.patch(
        "app.routers.ai_portfolio_construction.service_build_portfolio.ai_build_portfolio",
        new=fail,
    ):
        response = client.post("/ai/build_portfolio", json=_build_request())

    assert response.status_code == 500
    assert response.json()["status"] == 500
    assert "data" not in response.json()


def test_async_build_lifecycle_returns_running_then_completed_construction(deferred_task_store):
    with mock.patch(
        "app.routers.ai_portfolio_construction.service_build_portfolio.ai_build_portfolio",
        new=_construction_for_request,
    ):
        started = client.post(
            "/ai/start_build_portfolio_async",
            json=_build_request(),
        )
        task_id = started.json()["extra"]["task_id"]
        running = client.post(
            "/ai/poll_build_portfolio_async",
            params={"task_id": task_id},
        )

        deferred_task_store.release()

        completed = client.post(
            "/ai/poll_build_portfolio_async",
            params={"task_id": task_id},
        )
        duplicate = client.post(
            "/ai/start_build_portfolio_async",
            json=_build_request(),
        )

    assert started.status_code == 202
    assert running.status_code == 202
    assert completed.status_code == 200
    assert completed.json()["extra"] == {"task_id": task_id, "state": "COMPLETED"}
    assert completed.json()["data"]["construction_mode"] == "Scratch"
    assert duplicate.json() == completed.json()


def test_async_build_start_distinguishes_missing_and_invalid_bodies():
    missing = client.post("/ai/start_build_portfolio_async")
    invalid = client.post("/ai/start_build_portfolio_async", json={})

    assert missing.status_code == 400
    assert missing.json()["status"] == 400
    assert invalid.status_code == 422
    assert isinstance(invalid.json()["detail"], list)


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (portfolio_verification.PortfolioInputError("invalid portfolio"), 422),
        (portfolio_verification.PortfolioVerificationError("verification unavailable"), 502),
        (services_construction.PortfolioConstructionAIError("construction unavailable"), 502),
        (RuntimeError("unexpected failure"), 500),
    ],
)
def test_async_build_failures_are_pollable_and_reused(
    deferred_task_store,
    error,
    expected_status,
):
    async def fail(**kwargs):
        raise error

    with mock.patch(
        "app.routers.ai_portfolio_construction.service_build_portfolio.ai_build_portfolio",
        new=fail,
    ):
        started = client.post(
            "/ai/start_build_portfolio_async",
            json=_build_request(),
        )
        task_id = started.json()["extra"]["task_id"]
        deferred_task_store.release()
        failed = client.post(
            "/ai/poll_build_portfolio_async",
            params={"task_id": task_id},
        )
        duplicate = client.post(
            "/ai/start_build_portfolio_async",
            json=_build_request(),
        )

    assert failed.status_code == expected_status
    assert failed.json()["extra"] == {"task_id": task_id, "state": "FAILED"}
    assert "data" not in failed.json()
    assert duplicate.status_code == expected_status
    assert duplicate.json()["extra"] == {"task_id": task_id, "state": "FAILED"}
