from unittest import mock

import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app
from app.models import ai_portfolio_construction as models_construction
from app.models import ai_portfolio_review as models_review
from app.services import msai_build_portfolio as services_construction
from app.services import msai_review_portfolio as services_review
from app.services import portfolio_verification
from tests import portfolio_construction_fixtures, portfolio_review_fixtures

client = TestClient(app)


@pytest.fixture(autouse=True)
def disable_ai_proxy(monkeypatch):
    monkeypatch.setattr(config.settings_finhub_proxy, "proxy_mode", "None")
    monkeypatch.setattr(config.settings_finhub_proxy, "url_ai_task_node", "")


def _position(ticker: str, shares: float) -> dict[str, object]:
    return {
        "ticker": ticker,
        "num_shares": shares,
        "avg_price": 100 if shares else 0,
    }


def _request_body(
    positions: list[dict[str, object]] | None = None,
    *,
    rebalance_plan: bool = False,
) -> dict[str, object]:
    return {
        "country": "US",
        "investor_theme": "Long-term growth. Total budget USD 500.",
        "current_allocation": positions or [],
        "rebalance_plan": rebalance_plan,
    }


async def _construct(*, portfolio, country, investor_theme):
    mode = "Seeded" if any(position.num_shares > 0 for position in portfolio) else "Scratch"
    result_data = portfolio_construction_fixtures.construction(mode=mode).model_dump(mode="python")
    result_data.update({"country": country, "investor_theme": investor_theme})
    return models_construction.PortfolioConstruction.model_validate(result_data)


async def _review(*, portfolio, country, investor_theme, rebalance_plan):
    result_data = portfolio_review_fixtures.review().model_dump(mode="python")
    result_data.update(
        {
            "country": country,
            "investor_theme": investor_theme,
            "rebalance_requested": rebalance_plan,
        }
    )
    return models_review.PortfolioReview.model_validate(result_data)


def _major_rebalance_review(
    *,
    country: str,
    investor_theme: str,
    rebalance_requested: bool,
) -> models_review.PortfolioReview:
    target_allocations = {
        "NASDAQ:AAPL": 0.7,
        "NASDAQ:MSFT": 0.2,
        "NASDAQ:GOOGL": 0.1,
    }
    result_data = portfolio_review_fixtures.review().model_dump(mode="python")
    result_data.update(
        {
            "country": country,
            "investor_theme": investor_theme,
            "target_turnover": 0.2,
            "rebalance_requested": rebalance_requested,
            "rebalance_recommended": "YES",
            "major_rebalance_reasons": [
                "The validated target requires at least 20% one-way turnover.",
            ],
        }
    )
    for target in result_data["target_portfolio"]:
        target["target_allocation"] = target_allocations[target["ticker"]]
    for holding_review in result_data["holding_reviews"]:
        holding_review["target_allocation"] = target_allocations[holding_review["ticker"]]
        holding_review["recommendation"] = "BUY_MORE" if holding_review["ticker"] == "NASDAQ:AAPL" else "HOLD"

    if rebalance_requested:
        result_data["action_plan"] = models_review.PortfolioReviewActionPlan(
            plan_type="Rebalance",
            budget=portfolio_review_fixtures.total_budget(),
            cash_ledger=models_review.PortfolioReviewCashLedger(
                new_money_budget=500,
                estimated_sale_proceeds=0,
                purchase_spend=500,
                unallocated_cash=0,
            ),
            summary="Use the new-money budget to move toward the major-rebalance target.",
            actions=[
                models_review.PortfolioReviewAction(
                    priority=1,
                    action="BUY_MORE",
                    ticker="NASDAQ:AAPL",
                    company_name="Apple Inc.",
                    current_allocation=0.5,
                    target_allocation=0.7,
                    quantity=5,
                    market_price=100,
                    estimated_amount=500,
                    instruction="BUY 5 additional whole shares.",
                    reasoning="The validated target increases the Apple allocation.",
                    reference_ids=[portfolio_review_fixtures.SOURCE_IDS[0]],
                ),
                models_review.PortfolioReviewAction(
                    priority=2,
                    action="HOLD",
                    ticker="NASDAQ:MSFT",
                    company_name="Microsoft Corporation",
                    current_allocation=0.3,
                    target_allocation=0.2,
                    market_price=120,
                    instruction="HOLD the current 5 whole shares.",
                    reasoning="No whole-share trade is funded for this position.",
                    reference_ids=[portfolio_review_fixtures.SOURCE_IDS[1]],
                ),
                models_review.PortfolioReviewAction(
                    priority=3,
                    action="HOLD",
                    ticker="NASDAQ:GOOGL",
                    company_name="Alphabet Inc.",
                    current_allocation=0.2,
                    target_allocation=0.1,
                    market_price=100,
                    instruction="HOLD the current 4 whole shares.",
                    reasoning="No whole-share trade is funded for this position.",
                    reference_ids=[portfolio_review_fixtures.SOURCE_IDS[2]],
                ),
            ],
        )
    else:
        result_data["action_plan"] = None

    return models_review.PortfolioReview.model_validate(result_data)


@pytest.mark.parametrize(
    ("positions", "expected_mode"),
    [
        ([], "Scratch"),
        (
            [
                _position("NASDAQ:AAPL", 10),
                _position("NASDAQ:MSFT", 0),
                _position("NASDAQ:GOOGL", 0),
            ],
            "Seeded",
        ),
        (
            [_position(f"NASDAQ:T{index:02d}", 1 if index < 7 else 0) for index in range(20)],
            "Seeded",
        ),
    ],
)
def test_at_most_thirty_five_percent_positive_positions_dispatches_to_construction(
    positions,
    expected_mode,
):
    with (
        mock.patch(
            "app.routers.ai_portfolio_review.services_construction.ai_build_portfolio",
            new=_construct,
        ),
        mock.patch(
            "app.routers.ai_portfolio_review.services_review.ai_review_portfolio",
            new=_review,
        ),
    ):
        response = client.post("/ai/analyze_portfolio", json=_request_body(positions))

    assert response.status_code == 200
    assert response.json()["data"]["result_type"] == "PortfolioConstruction"
    assert response.json()["data"]["construction_mode"] == expected_mode


def test_more_than_thirty_five_percent_positive_positions_dispatches_to_review():
    positions = [
        _position("NASDAQ:AAPL", 10),
        _position("NASDAQ:MSFT", 5),
        _position("NASDAQ:GOOGL", 4),
    ]
    with (
        mock.patch(
            "app.routers.ai_portfolio_review.services_construction.ai_build_portfolio",
            new=_construct,
        ),
        mock.patch(
            "app.routers.ai_portfolio_review.services_review.ai_review_portfolio",
            new=_review,
        ),
    ):
        response = client.post(
            "/ai/analyze_portfolio",
            json=_request_body(positions, rebalance_plan=True),
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["result_type"] == "PortfolioReview"
    assert data["rebalance_requested"] is True
    assert data["rebalance_recommended"] == "NO"
    assert data["action_plan"]["plan_type"] == "Growth"
    assert [holding["ticker"] for holding in data["snapshot"]["holdings"]] == [
        "NASDAQ:AAPL",
        "NASDAQ:MSFT",
        "NASDAQ:GOOGL",
    ]


@pytest.mark.parametrize(
    ("rebalance_requested", "rebalance_recommended", "expected_plan_type"),
    [
        (False, "NO", "Growth"),
        (True, "NO", "Growth"),
        (False, "YES", None),
        (True, "YES", "Rebalance"),
    ],
)
def test_review_response_exposes_documented_rebalance_plan_variants(
    rebalance_requested,
    rebalance_recommended,
    expected_plan_type,
):
    positions = [
        _position("NASDAQ:AAPL", 10),
        _position("NASDAQ:MSFT", 5),
        _position("NASDAQ:GOOGL", 4),
    ]

    async def review_variant(*, portfolio, country, investor_theme, rebalance_plan):
        if rebalance_recommended == "YES":
            return _major_rebalance_review(
                country=country,
                investor_theme=investor_theme,
                rebalance_requested=rebalance_plan,
            )
        return await _review(
            portfolio=portfolio,
            country=country,
            investor_theme=investor_theme,
            rebalance_plan=rebalance_plan,
        )

    with mock.patch(
        "app.routers.ai_portfolio_review.services_review.ai_review_portfolio",
        new=review_variant,
    ):
        response = client.post(
            "/ai/analyze_portfolio",
            json=_request_body(positions, rebalance_plan=rebalance_requested),
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["rebalance_requested"] is rebalance_requested
    assert data["rebalance_recommended"] == rebalance_recommended
    if expected_plan_type is None:
        assert data["action_plan"] is None
    else:
        assert data["action_plan"]["plan_type"] == expected_plan_type


@pytest.mark.parametrize(
    "body",
    [
        {"country": "US", "current_allocation": []},
        _request_body(
            [
                _position("NASDAQ:AAPL", 1),
                _position("nasdaq:aapl", 2),
            ]
        ),
        {**_request_body(), "investor_theme": "   "},
    ],
)
def test_analyze_portfolio_rejects_invalid_dispatch_requests(body):
    response = client.post("/ai/analyze_portfolio", json=body)

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)


@pytest.mark.parametrize(
    ("branch", "error", "expected_status"),
    [
        ("construction", portfolio_verification.PortfolioInputError("invalid input"), 422),
        (
            "construction",
            portfolio_verification.PortfolioVerificationError("verification unavailable"),
            502,
        ),
        (
            "construction",
            services_construction.PortfolioConstructionAIError("construction unavailable"),
            502,
        ),
        ("review", portfolio_verification.PortfolioInputError("invalid input"), 422),
        ("review", portfolio_verification.PortfolioVerificationError("verification unavailable"), 502),
        ("review", services_review.PortfolioReviewAIError("review unavailable"), 502),
    ],
)
def test_analyze_portfolio_maps_selected_branch_failures(branch, error, expected_status):
    async def fail(**kwargs):
        raise error

    positions = (
        []
        if branch == "construction"
        else [
            _position("NASDAQ:AAPL", 10),
            _position("NASDAQ:MSFT", 5),
            _position("NASDAQ:GOOGL", 4),
        ]
    )
    with (
        mock.patch(
            "app.routers.ai_portfolio_review.services_construction.ai_build_portfolio",
            new=fail if branch == "construction" else _construct,
        ),
        mock.patch(
            "app.routers.ai_portfolio_review.services_review.ai_review_portfolio",
            new=fail if branch == "review" else _review,
        ),
    ):
        response = client.post("/ai/analyze_portfolio", json=_request_body(positions))

    assert response.status_code == expected_status
    assert response.json()["status"] == expected_status
    assert "data" not in response.json()


@pytest.mark.parametrize(
    ("body", "expected_type"),
    [
        (_request_body([]), "PortfolioConstruction"),
        (
            _request_body(
                [
                    _position("NASDAQ:AAPL", 10),
                    _position("NASDAQ:MSFT", 5),
                    _position("NASDAQ:GOOGL", 4),
                ]
            ),
            "PortfolioReview",
        ),
    ],
)
def test_async_dispatch_lifecycle_returns_the_selected_completed_result(
    deferred_task_store,
    body,
    expected_type,
):
    with (
        mock.patch(
            "app.routers.ai_portfolio_review.services_construction.ai_build_portfolio",
            new=_construct,
        ),
        mock.patch(
            "app.routers.ai_portfolio_review.services_review.ai_review_portfolio",
            new=_review,
        ),
    ):
        started = client.post("/ai/start_analyze_portfolio_async", json=body)
        task_id = started.json()["extra"]["task_id"]
        running = client.post(
            "/ai/poll_analyze_portfolio_async",
            params={"task_id": task_id},
        )
        deferred_task_store.release()
        completed = client.post(
            "/ai/poll_analyze_portfolio_async",
            params={"task_id": task_id},
        )
        duplicate = client.post("/ai/start_analyze_portfolio_async", json=body)

    assert started.status_code == 202
    assert running.status_code == 202
    assert completed.status_code == 200
    assert completed.json()["data"]["result_type"] == expected_type
    assert completed.json()["extra"] == {"task_id": task_id, "state": "COMPLETED"}
    assert duplicate.json() == completed.json()


def test_async_dispatch_start_distinguishes_missing_and_invalid_bodies():
    missing = client.post("/ai/start_analyze_portfolio_async")
    invalid = client.post("/ai/start_analyze_portfolio_async", json={})

    assert missing.status_code == 400
    assert missing.json()["status"] == 400
    assert invalid.status_code == 422
    assert isinstance(invalid.json()["detail"], list)


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (portfolio_verification.PortfolioInputError("invalid input"), 422),
        (portfolio_verification.PortfolioVerificationError("verification unavailable"), 502),
        (services_review.PortfolioReviewAIError("review unavailable"), 502),
        (RuntimeError("unexpected failure"), 500),
    ],
)
def test_async_review_failures_are_pollable_and_reused(
    deferred_task_store,
    error,
    expected_status,
):
    async def fail(**kwargs):
        raise error

    positions = [
        _position("NASDAQ:AAPL", 10),
        _position("NASDAQ:MSFT", 5),
        _position("NASDAQ:GOOGL", 4),
    ]
    body = _request_body(positions)
    with mock.patch(
        "app.routers.ai_portfolio_review.services_review.ai_review_portfolio",
        new=fail,
    ):
        started = client.post("/ai/start_analyze_portfolio_async", json=body)
        task_id = started.json()["extra"]["task_id"]
        deferred_task_store.release()
        failed = client.post(
            "/ai/poll_analyze_portfolio_async",
            params={"task_id": task_id},
        )
        duplicate = client.post("/ai/start_analyze_portfolio_async", json=body)

    assert failed.status_code == expected_status
    assert failed.json()["extra"] == {"task_id": task_id, "state": "FAILED"}
    assert duplicate.status_code == expected_status
    assert duplicate.json()["extra"] == {"task_id": task_id, "state": "FAILED"}
