import pytest
from pydantic import ValidationError

from app.models import ai_portfolio_construction as models_construction
from tests import portfolio_construction_fixtures as fixtures


def test_new_money_action_plan_rejects_trim():
    total_plan = fixtures.construction(mode="Seeded").action_plan
    assert total_plan is not None
    trim_step = total_plan.steps[0].model_copy(
        update={
            "action": "TRIM",
            "quantity": 1,
            "market_price": 200,
            "estimated_amount": 200,
        }
    )

    with pytest.raises(ValidationError, match="cannot contain TRIM"):
        models_construction.PortfolioActionPlan(
            budget=fixtures.recurring_budget(),
            summary=total_plan.summary,
            budget_utilized=200,
            unallocated_amount=800,
            steps=[trim_step, *total_plan.steps[1:]],
        )


def test_action_plan_requires_consecutive_priorities():
    plan = fixtures.action_plan()
    invalid_steps = [
        plan.steps[0],
        plan.steps[1].model_copy(update={"priority": 3}),
        plan.steps[2].model_copy(update={"priority": 4}),
    ]

    with pytest.raises(ValidationError, match="consecutive"):
        models_construction.PortfolioActionPlan(
            budget=plan.budget,
            summary=plan.summary,
            budget_utilized=None,
            unallocated_amount=None,
            steps=invalid_steps,
        )


def test_construction_requires_actions_for_every_target():
    construction = fixtures.construction()
    assert construction.action_plan is not None
    incomplete_plan = construction.action_plan.model_copy(update={"steps": construction.action_plan.steps[:-1]})

    with pytest.raises(ValidationError, match="cover every target"):
        models_construction.PortfolioConstruction(
            **construction.model_dump(exclude={"action_plan"}),
            action_plan=incomplete_plan,
        )


def test_scratch_construction_allows_null_action_plan():
    construction = fixtures.construction()

    result = models_construction.PortfolioConstruction(
        **construction.model_dump(exclude={"action_plan"}),
        action_plan=None,
    )

    assert result.action_plan is None
    assert result.model_dump(exclude_none=True)["action_plan"] is None
    assert result.model_dump(include={"country"}, exclude_none=True) == {"country": "US"}


def test_seeded_construction_rejects_null_action_plan():
    construction = fixtures.construction(mode="Seeded")

    with pytest.raises(ValidationError, match="requires an action plan"):
        models_construction.PortfolioConstruction(
            **construction.model_dump(exclude={"action_plan"}),
            action_plan=None,
        )
