import datetime

import pydantic
import pytest

from app.models import events_div as models_dividends
from tests import dividend_fixtures


def test_numeric_range_accepts_ordered_bounds_and_serializes():
    price_range = models_dividends.DividendNumericRange(minimum=1.0, maximum=2.0)

    assert price_range.model_dump(mode="json") == {"minimum": 1.0, "maximum": 2.0}


def test_numeric_range_rejects_reversed_bounds():
    with pytest.raises(pydantic.ValidationError):
        models_dividends.DividendNumericRange(minimum=2.0, maximum=1.0)


def test_recovery_rejects_positive_probability_without_days():
    data = dividend_fixtures.recovery_estimate(dividend_fixtures.numeric_range(100.0)).model_dump(mode="python")
    data["days"] = None

    with pytest.raises(pydantic.ValidationError):
        models_dividends.DividendRecoveryEstimate.model_validate(data)


def test_recovery_rejects_date_without_recovery_days():
    data = {
        "target_price": dividend_fixtures.numeric_range(100.0).model_dump(mode="python"),
        "success_probability": 0.0,
        "days": None,
        "estimated_date_min": datetime.date(2026, 6, 16),
        "estimated_date_max": None,
    }

    with pytest.raises(pydantic.ValidationError):
        models_dividends.DividendRecoveryEstimate.model_validate(data)


def test_failed_analysis_preserves_baseline_without_strategy_results():
    analysis = dividend_fixtures.failed_analysis()

    serialized = analysis.model_dump(mode="json")
    assert serialized["analysis_status"] == "Failed"
    assert serialized["historical_baseline"]["sample_count"] == 5
    assert serialized["evidence_adjusted_ex_date_close_drop"] is None
    assert serialized["evidence_adjusted_pre_ex_close_recovery"] is None
    assert serialized["evidence_adjusted_capture_break_even_recovery"] is None
    assert serialized["evidence_adjusted_discount_break_even_recovery"] is None
    assert serialized["dividend_capture"] is None
    assert serialized["recommendation"] is None


def test_complete_analysis_allows_null_evidence_adjusted_estimates_for_insufficient_insights():
    analysis_data = dividend_fixtures.complete_analysis().model_dump(mode="python")
    analysis_data["evidence_adjusted_ex_date_close_drop"] = None
    analysis_data["evidence_adjusted_pre_ex_close_recovery"] = None
    analysis_data["evidence_adjusted_capture_break_even_recovery"] = None
    analysis_data["evidence_adjusted_discount_break_even_recovery"] = None
    analysis_data["recommendation"]["outcome"] = "InsufficientInsights"

    analysis = models_dividends.DividendEventAnalysis.model_validate(analysis_data)

    serialized = analysis.model_dump(mode="json")
    assert analysis.analysis_status == "Complete"
    assert serialized["evidence_adjusted_ex_date_close_drop"] is None
    assert serialized["evidence_adjusted_pre_ex_close_recovery"] is None
    assert serialized["evidence_adjusted_capture_break_even_recovery"] is None
    assert serialized["evidence_adjusted_discount_break_even_recovery"] is None


def test_complete_analysis_accepts_referenced_source_registry():
    analysis = dividend_fixtures.complete_analysis()

    source_id = analysis.references[0].id
    assert source_id in analysis.research.dividend_terms.reference_ids
    assert [item["id"] for item in analysis.model_dump(mode="json")["references"]] == [
        reference.id for reference in analysis.references
    ]


def test_event_context_normalizes_documented_identifiers():
    context_data = dividend_fixtures.event_context().model_dump(mode="python")
    context_data.update(
        {
            "symbol": " asx:cba ",
            "exchange": " asx ",
            "currency": " aud ",
            "country": " Australia ",
        }
    )

    context = models_dividends.DividendEventContext.model_validate(context_data)

    assert context.symbol == "ASX:CBA"
    assert context.exchange == "ASX"
    assert context.currency == "AUD"
    assert context.country == "Australia"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("currency", "U$D"),
        ("exchange", "NYSE"),
        ("exchange", "NEW YORK"),
        ("gross_dividend_yield", 0.03),
    ],
)
def test_event_context_rejects_invalid_documented_value(field, value):
    context_data = dividend_fixtures.event_context().model_dump(mode="python")
    context_data["symbol"] = "ASX:CBA"
    context_data[field] = value

    with pytest.raises(pydantic.ValidationError):
        models_dividends.DividendEventContext.model_validate(context_data)


def test_event_phase_rejects_value_inconsistent_with_exchange_local_date():
    context_data = dividend_fixtures.event_context().model_dump(mode="python")
    context_data["phase"] = "Historical"

    with pytest.raises(pydantic.ValidationError):
        models_dividends.DividendEventContext.model_validate(context_data)


def test_eligible_strategy_accepts_zero_probability_without_recovery_days():
    strategy_data = dividend_fixtures.strategy("DividendCapture").model_dump(mode="python")
    strategy_data["success_probability"] = 0.0
    strategy_data["recovery_days"] = None

    strategy = models_dividends.DividendStrategyAssessment.model_validate(strategy_data)

    assert strategy.eligibility == "Eligible"
    assert strategy.model_dump(mode="json")["recovery_days"] is None


def test_ineligible_strategy_rejects_estimates():
    strategy_data = dividend_fixtures.strategy(
        "DividendCapture",
        eligibility="Ineligible",
    ).model_dump(mode="python")
    strategy_data["expected_entry_price"] = dividend_fixtures.numeric_range(100.0).model_dump(mode="python")

    with pytest.raises(pydantic.ValidationError):
        models_dividends.DividendStrategyAssessment.model_validate(strategy_data)
