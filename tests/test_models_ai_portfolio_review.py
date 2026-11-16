import copy

import pydantic
import pytest

from app.models import ai_portfolio_review as models_review
from app.schemas import ai_portfolio_review as schemas_review
from tests import portfolio_construction_fixtures
from tests import portfolio_review_fixtures as fixtures


def _major_review_data() -> dict[str, object]:
    data = fixtures.review().model_dump(mode="python")
    data["target_portfolio"] = [
        {
            **data["target_portfolio"][0],
            "target_allocation": 0.6,
        },
        {
            **data["target_portfolio"][1],
            "target_allocation": 0.4,
        },
    ]
    data["holding_reviews"][0]["target_allocation"] = 0.6
    data["holding_reviews"][0]["recommendation"] = "BUY_MORE"
    data["holding_reviews"][1]["target_allocation"] = 0.4
    data["holding_reviews"][1]["recommendation"] = "BUY_MORE"
    data["holding_reviews"][2]["target_allocation"] = 0
    data["holding_reviews"][2]["recommendation"] = "EXIT"
    data["holding_reviews"][2]["exit_reason"] = "CriticalRisk"
    data["target_turnover"] = 0.2
    data["rebalance_requested"] = False
    data["rebalance_recommended"] = "YES"
    data["major_rebalance_reasons"] = ["NASDAQ:GOOGL requires EXIT due to validated critical risk."]
    data["action_plan"] = None
    return data


def test_review_accepts_and_serializes_complete_growth_plan():
    review = fixtures.review()

    serialized = review.model_dump(mode="json")
    assert serialized["result_type"] == "PortfolioReview"
    assert serialized["rebalance_recommended"] == "NO"
    assert serialized["action_plan"]["plan_type"] == "Growth"
    assert all(item["role"] for item in serialized["holding_reviews"])


def test_recommended_unrequested_rebalance_preserves_null_action_plan():
    review = models_review.PortfolioReview.model_validate(_major_review_data())

    assert review.rebalance_recommended == "YES"
    assert review.action_plan is None
    assert review.model_dump(mode="json", exclude_none=True)["action_plan"] is None


def test_exact_twenty_percent_turnover_requires_rebalance():
    data = _major_review_data()
    data["rebalance_recommended"] = "NO"

    with pytest.raises(pydantic.ValidationError):
        models_review.PortfolioReview.model_validate(data)


def test_recommended_requested_rebalance_requires_action_plan():
    data = _major_review_data()
    data["rebalance_requested"] = True

    with pytest.raises(pydantic.ValidationError):
        models_review.PortfolioReview.model_validate(data)


def test_no_rebalance_requires_growth_plan_for_requested_actions():
    data = fixtures.review().model_dump(mode="python")
    data["rebalance_requested"] = True
    review = models_review.PortfolioReview.model_validate(data)
    assert review.action_plan is not None
    assert review.action_plan.plan_type == "Growth"

    data["action_plan"]["plan_type"] = "Rebalance"
    with pytest.raises(pydantic.ValidationError):
        models_review.PortfolioReview.model_validate(data)


def test_long_term_review_rejects_trim_recommendation():
    data = fixtures.review().model_dump(mode="python")
    data["holding_reviews"][0]["recommendation"] = "TRIM"

    with pytest.raises(pydantic.ValidationError):
        models_review.PortfolioReview.model_validate(data)


def test_swing_review_accepts_risk_control_exit():
    data = _major_review_data()
    data["strategy"] = "Swing"
    data["holding_reviews"][2]["exit_reason"] = "SwingRiskControl"

    review = models_review.PortfolioReview.model_validate(data)

    assert review.model_dump(mode="json")["holding_reviews"][2]["exit_reason"] == "SwingRiskControl"


def test_review_rejects_unknown_referenced_source():
    data = fixtures.review().model_dump(mode="python")
    data["strengths"][0]["reference_ids"] = ["src-unknown"]

    with pytest.raises(pydantic.ValidationError):
        models_review.PortfolioReview.model_validate(data)


def test_action_plan_rejects_unbalanced_cash_ledger():
    plan = fixtures.review().action_plan
    assert plan is not None
    data = plan.model_dump(mode="python")
    data["cash_ledger"]["unallocated_cash"] = 99

    with pytest.raises(pydantic.ValidationError):
        models_review.PortfolioReviewActionPlan.model_validate(data)


@pytest.mark.parametrize("prefix", ["🚀", "🛡️", "🧭", "🧱", "⚡", "💵"])
def test_review_roles_accept_documented_prefixes(prefix):
    review = fixtures.review()
    model_and_data = (
        (
            models_review.PortfolioHoldingReview,
            review.holding_reviews[0].model_dump(mode="python"),
        ),
        (
            models_review.PortfolioReviewTargetPosition,
            review.target_portfolio[0].model_dump(mode="python"),
        ),
    )

    for model_type, data in model_and_data:
        data["role"] = f"{prefix} Documented portfolio role"
        assert model_type.model_validate(data).role.startswith(prefix)


@pytest.mark.parametrize(
    ("model_type", "item"),
    [
        (models_review.PortfolioHoldingReview, "holding_reviews"),
        (models_review.PortfolioReviewTargetPosition, "target_portfolio"),
    ],
)
def test_review_roles_reject_unsupported_prefix(model_type, item):
    data = getattr(fixtures.review(), item)[0].model_dump(mode="python")
    data["role"] = "📈 Unsupported role"

    with pytest.raises(pydantic.ValidationError):
        model_type.model_validate(data)


def test_review_snapshot_normalizes_iso_country_and_currency_codes():
    data = fixtures.review().snapshot.model_dump(mode="python")
    data["country"] = " us "
    data["currency"] = " usd "
    for holding in data["holdings"]:
        holding["currency"] = " usd "

    snapshot = models_review.PortfolioReviewSnapshot.model_validate(data)

    assert snapshot.country == "US"
    assert snapshot.currency == "USD"
    assert {holding.currency for holding in snapshot.holdings} == {"USD"}


@pytest.mark.parametrize(("field", "value"), [("country", "ZZ"), ("currency", "U$D")])
def test_review_snapshot_rejects_invalid_identifier(field, value):
    data = fixtures.review().snapshot.model_dump(mode="python")
    data[field] = value

    with pytest.raises(pydantic.ValidationError):
        models_review.PortfolioReviewSnapshot.model_validate(data)


@pytest.mark.parametrize(
    "result",
    [fixtures.review(), portfolio_construction_fixtures.construction()],
    ids=["review", "construction"],
)
def test_analyze_portfolio_response_serializes_supported_result(result):
    response = schemas_review.AnalyzePortfolioResponse(
        status=200,
        message="Portfolio analysis completed.",
        data=result,
    )

    serialized = response.model_dump(mode="json")
    assert serialized["data"]["result_type"] == result.result_type


def test_analyze_portfolio_request_normalizes_and_serializes_valid_holdings():
    request = schemas_review.AnalyzePortfolioRequest(
        country=" US ",
        investor_theme=" Long-term growth ",
        current_allocation=[fixtures.holdings()[0]],
    )

    assert request.model_dump(mode="json") == {
        "country": "US",
        "current_allocation": [fixtures.holdings()[0].model_dump(mode="json")],
        "investor_theme": "Long-term growth",
        "rebalance_plan": False,
    }


def test_analyze_portfolio_request_rejects_blank_theme():
    with pytest.raises(pydantic.ValidationError):
        schemas_review.AnalyzePortfolioRequest(country="US", investor_theme=" ")


def test_analyze_portfolio_request_rejects_duplicate_tickers():
    holding_data = fixtures.holdings()[0].model_dump(mode="python")

    with pytest.raises(pydantic.ValidationError):
        schemas_review.AnalyzePortfolioRequest(
            country="US",
            investor_theme="Long-term growth",
            current_allocation=[holding_data, holding_data],
        )


def test_analyze_portfolio_request_rejects_fractional_positive_holding():
    fractional = copy.deepcopy(fixtures.holdings()[0].model_dump(mode="python"))
    fractional["num_shares"] = 1.5

    with pytest.raises(pydantic.ValidationError):
        schemas_review.AnalyzePortfolioRequest(
            country="US",
            investor_theme="Long-term growth",
            current_allocation=[fractional],
        )
