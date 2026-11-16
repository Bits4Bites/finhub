import pydantic
import pytest

from app.models import ai_portfolio_construction as models_construction
from tests import portfolio_construction_fixtures as fixtures


def test_new_money_action_plan_rejects_valid_trim_action():
    plan_data = fixtures.action_plan().model_dump(mode="python")
    trim_data = {
        **plan_data["steps"][0],
        "action": "TRIM",
        "instruction": "TRIM 1 whole share.",
        "quantity": 1,
        "market_price": 200,
        "estimated_amount": 200,
    }
    trim_step = models_construction.PortfolioActionStep.model_validate(trim_data)
    plan_data["steps"][0] = trim_step.model_dump(mode="python")

    with pytest.raises(pydantic.ValidationError):
        models_construction.PortfolioActionPlan.model_validate(plan_data)


def test_action_plan_rejects_nonconsecutive_priorities():
    plan_data = fixtures.action_plan().model_dump(mode="python")
    plan_data["steps"][1]["priority"] = 4

    with pytest.raises(pydantic.ValidationError):
        models_construction.PortfolioActionPlan.model_validate(plan_data)


def test_construction_rejects_action_plan_missing_a_target():
    construction_data = fixtures.construction().model_dump(mode="python")
    construction_data["action_plan"]["steps"] = construction_data["action_plan"]["steps"][:-1]

    with pytest.raises(pydantic.ValidationError):
        models_construction.PortfolioConstruction.model_validate(construction_data)


def test_scratch_construction_accepts_and_serializes_null_action_plan():
    construction = fixtures.construction(action_plan_available=False)

    assert construction.action_plan is None
    assert construction.data_gaps == [
        "Investment budget and current holdings were not supplied; an action plan cannot be built."
    ]
    assert construction.model_dump(mode="json", exclude_none=True)["action_plan"] is None


def test_seeded_construction_rejects_null_action_plan():
    construction_data = fixtures.construction(mode="Seeded").model_dump(mode="python")
    construction_data["action_plan"] = None

    with pytest.raises(pydantic.ValidationError):
        models_construction.PortfolioConstruction.model_validate(construction_data)


def test_construction_normalizes_iso_country_code():
    construction_data = fixtures.construction().model_dump(mode="python")
    construction_data["country"] = " us "

    construction = models_construction.PortfolioConstruction.model_validate(construction_data)

    assert construction.country == "US"


def test_construction_rejects_unknown_iso_country_code():
    construction_data = fixtures.construction().model_dump(mode="python")
    construction_data["country"] = "ZZ"

    with pytest.raises(pydantic.ValidationError):
        models_construction.PortfolioConstruction.model_validate(construction_data)
