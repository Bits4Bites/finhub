from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.models import ai_portfolio_review as models_review
from app.schemas import ai_portfolio_review as schemas_review
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


def test_review_accepts_complete_structured_growth_plan():
    review = fixtures.review()

    assert review.result_type == "PortfolioReview"
    assert review.rebalance_recommended == "NO"
    assert review.action_plan is not None
    assert review.action_plan.plan_type == "Growth"
    assert all(holding.role.startswith(models_review.ROLE_PREFIXES) for holding in review.holding_reviews)


def test_recommended_unrequested_rebalance_preserves_explicit_null_action_plan():
    review = models_review.PortfolioReview.model_validate(_major_review_data())

    assert review.rebalance_recommended == "YES"
    assert review.action_plan is None
    assert review.model_dump(exclude_none=True)["action_plan"] is None
    assert review.model_dump(include={"country"}, exclude_none=True) == {"country": "US"}


def test_exact_twenty_percent_turnover_requires_rebalance():
    data = _major_review_data()
    data["rebalance_recommended"] = "NO"
    data["major_rebalance_reasons"] = []

    with pytest.raises(ValidationError, match="rebalance_recommended"):
        models_review.PortfolioReview.model_validate(data)


def test_recommended_requested_rebalance_requires_rebalance_plan():
    data = _major_review_data()
    data["rebalance_requested"] = True

    with pytest.raises(ValidationError, match="requires an action plan"):
        models_review.PortfolioReview.model_validate(data)


def test_no_rebalance_requires_growth_plan_for_both_request_flags():
    data = fixtures.review().model_dump(mode="python")
    data["rebalance_requested"] = True
    review = models_review.PortfolioReview.model_validate(data)
    assert review.action_plan is not None
    assert review.action_plan.plan_type == "Growth"

    data["action_plan"]["plan_type"] = "Rebalance"
    with pytest.raises(ValidationError, match="plan type"):
        models_review.PortfolioReview.model_validate(data)


def test_long_term_review_rejects_trim_recommendation():
    data = fixtures.review().model_dump(mode="python")
    data["holding_reviews"][0]["recommendation"] = "TRIM"

    with pytest.raises(ValidationError, match="LongTerm holding reviews cannot recommend TRIM"):
        models_review.PortfolioReview.model_validate(data)


def test_swing_review_allows_risk_control_exit():
    data = _major_review_data()
    data["strategy"] = "Swing"
    data["holding_reviews"][2]["exit_reason"] = "SwingRiskControl"

    review = models_review.PortfolioReview.model_validate(data)

    assert review.holding_reviews[2].exit_reason == "SwingRiskControl"


def test_review_rejects_unknown_reference_id():
    data = fixtures.review().model_dump(mode="python")
    data["strengths"][0]["reference_ids"] = ["src-unknown"]

    with pytest.raises(ValidationError, match="unknown reference IDs"):
        models_review.PortfolioReview.model_validate(data)


def test_action_plan_rejects_unbalanced_cash_ledger():
    plan = fixtures.review().action_plan
    assert plan is not None
    data = plan.model_dump(mode="python")
    data["cash_ledger"]["unallocated_cash"] = 99

    with pytest.raises(ValidationError, match="must balance"):
        models_review.PortfolioReviewActionPlan.model_validate(data)


def test_analyze_portfolio_schema_uses_result_discriminator():
    schema = schemas_review.AnalyzePortfolioResponse.model_json_schema()
    data_schema = schema["properties"]["data"]["anyOf"][0]

    assert data_schema["discriminator"]["propertyName"] == "result_type"
    assert set(data_schema["discriminator"]["mapping"]) == {
        "PortfolioConstruction",
        "PortfolioReview",
    }


def test_analyze_portfolio_request_requires_theme_and_unique_whole_share_holdings():
    with pytest.raises(ValidationError):
        schemas_review.AnalyzePortfolioRequest(country="US", investor_theme=" ")

    duplicate_holdings = [holding.model_dump() for holding in fixtures.holdings()[:1]] * 2
    with pytest.raises(ValidationError, match="tickers must be unique"):
        schemas_review.AnalyzePortfolioRequest(
            country="US",
            investor_theme="Long-term growth",
            current_allocation=duplicate_holdings,
        )

    fractional = deepcopy(fixtures.holdings()[0].model_dump())
    fractional["num_shares"] = 1.5
    with pytest.raises(ValidationError, match="whole-share"):
        schemas_review.AnalyzePortfolioRequest(
            country="US",
            investor_theme="Long-term growth",
            current_allocation=[fractional],
        )
