from datetime import date

import pytest
from pydantic import ValidationError

from app.models import events_dividends as models_dividends
from tests import dividend_fixtures


def test_numeric_range_rejects_reversed_bounds():
    with pytest.raises(ValidationError, match="minimum must not exceed maximum"):
        models_dividends.DividendNumericRange(minimum=2.0, maximum=1.0)


def test_recovery_requires_days_when_probability_is_positive():
    with pytest.raises(ValidationError, match="positive recovery probability"):
        models_dividends.DividendRecoveryEstimate(
            target_price=dividend_fixtures.numeric_range(100.0),
            success_probability=0.5,
            days=None,
            estimated_date_min=None,
            estimated_date_max=None,
        )


def test_recovery_rejects_dates_without_days():
    with pytest.raises(ValidationError, match="recovery days and estimated dates"):
        models_dividends.DividendRecoveryEstimate(
            target_price=dividend_fixtures.numeric_range(100.0),
            success_probability=0.0,
            days=None,
            estimated_date_min=date(2026, 6, 16),
            estimated_date_max=date(2026, 6, 17),
        )


def test_failed_analysis_preserves_baseline_without_strategy():
    analysis = dividend_fixtures.failed_analysis()

    assert analysis.analysis_status == "Failed"
    assert analysis.historical_baseline.sample_count == 5
    assert analysis.dividend_capture is None
    assert analysis.recommendation is None


def test_complete_analysis_validates_reference_registry():
    analysis = dividend_fixtures.complete_analysis()

    assert analysis.analysis_status == "Complete"
    assert analysis.references[0].id == dividend_fixtures.SOURCE_ID


def test_event_phase_must_match_exchange_local_date():
    context_data = dividend_fixtures.event_context().model_dump()
    context_data["phase"] = "Historical"

    with pytest.raises(ValidationError, match="event phase is inconsistent"):
        models_dividends.DividendEventContext.model_validate(context_data)


def test_eligible_strategy_allows_zero_probability_without_recovery_days():
    strategy = dividend_fixtures.strategy("DividendCapture").model_copy(
        update={
            "success_probability": 0.0,
            "recovery_days": None,
        }
    )

    validated = models_dividends.DividendStrategyAssessment.model_validate(strategy.model_dump())

    assert validated.eligibility == "Eligible"
    assert validated.recovery_days is None


def test_ineligible_strategy_rejects_estimates():
    strategy_data = dividend_fixtures.strategy("DividendCapture").model_dump()
    strategy_data["eligibility"] = "Ineligible"
    strategy_data["ineligibility_reason"] = "The ex-date has passed."

    with pytest.raises(ValidationError, match="cannot contain estimates"):
        models_dividends.DividendStrategyAssessment.model_validate(strategy_data)
