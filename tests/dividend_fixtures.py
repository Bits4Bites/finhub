from datetime import UTC, date, datetime

from app.models import ai as models_ai
from app.models import events_dividends as models_dividends
from app.models import types

SOURCE_ID = "src-0123456789abcdef0123456789abcdef"
EX_DATE = date(2026, 6, 15)


def numeric_range(minimum: float, maximum: float | None = None) -> models_dividends.DividendNumericRange:
    return models_dividends.DividendNumericRange(
        minimum=minimum,
        maximum=minimum if maximum is None else maximum,
    )


def drop_estimate() -> models_dividends.DividendDropEstimate:
    return models_dividends.DividendDropEstimate(
        drop_amount=numeric_range(1.0, 2.0),
        drop_percent=numeric_range(0.01, 0.02),
        drop_to_dividend_ratio=numeric_range(0.5, 1.0),
        estimated_price=numeric_range(98.0, 99.0),
    )


def recovery_estimate(
    target: models_dividends.DividendNumericRange,
    *,
    probability: float = 0.7,
    minimum_days: int = 1,
    maximum_days: int = 3,
) -> models_dividends.DividendRecoveryEstimate:
    return models_dividends.DividendRecoveryEstimate(
        target_price=target,
        success_probability=probability,
        days=models_dividends.DividendDayRange(
            minimum=minimum_days,
            maximum=maximum_days,
        ),
        estimated_date_min=EX_DATE.replace(day=EX_DATE.day + minimum_days),
        estimated_date_max=EX_DATE.replace(day=EX_DATE.day + maximum_days),
    )


def event_context(
    *,
    phase: models_dividends.DividendEventPhase = "BeforeExDate",
) -> models_dividends.DividendEventContext:
    as_of_by_phase = {
        "BeforeExDate": datetime(2026, 5, 28, 0, 0, tzinfo=UTC),
        "ExDate": datetime(2026, 6, 15, 0, 0, tzinfo=UTC),
        "PostExDate": datetime(2026, 6, 16, 0, 0, tzinfo=UTC),
        "Historical": datetime(2026, 7, 20, 0, 0, tzinfo=UTC),
    }
    return models_dividends.DividendEventContext(
        symbol="CBA.AX",
        exchange="ASX",
        company_name="Commonwealth Bank",
        currency="AUD",
        country="Australia",
        asset_type=types.STANDARD_ASSET,
        exchange_timezone="Australia/Sydney",
        ex_date=EX_DATE,
        phase=phase,
        as_of=as_of_by_phase[phase],
        reference_price=100.0,
        dividend_amount=2.0,
        gross_dividend_yield=0.02,
        holding_period_days=28,
        transaction_costs=models_dividends.DividendTransactionCosts(),
    )


def historical_baseline(
    *,
    sample_count: int = 5,
) -> models_dividends.DividendHistoricalBaseline:
    return models_dividends.DividendHistoricalBaseline(
        sample_count=sample_count,
        sample_quality="Sufficient" if sample_count >= 4 else "Limited",
        quality_flags=[] if sample_count >= 4 else ["Limited historical sample."],
        ex_date_open_drop=drop_estimate(),
        ex_date_close_drop=drop_estimate(),
        ex_date_intraday_low_drop=drop_estimate(),
        post_ex_date_drawdown=drop_estimate(),
        pre_ex_close_recovery=recovery_estimate(numeric_range(100.0)),
        dividend_capture_break_even_recovery=recovery_estimate(numeric_range(98.0)),
        post_dividend_discount_break_even_recovery=recovery_estimate(numeric_range(98.0)),
        technical_context=models_dividends.DividendTechnicalContext(
            beta=1.0,
            rsi14=50.0,
            average_daily_value_traded_7d=1_000_000.0,
            average_volume_30d=100_000.0,
            daily_return_volatility_30d=0.02,
            bid_ask_spread=0.01,
            stock_trend_60d=0.02,
            market_trend_60d=0.01,
            peer_trend_60d=0.015,
        ),
    )


def reference(*, verified: bool = True) -> models_ai.ReferenceSource:
    return models_ai.ReferenceSource(
        id=SOURCE_ID,
        title="Dividend announcement",
        publisher="ASX",
        source_type="Exchange",
        published_at=datetime(2026, 5, 20, tzinfo=UTC),
        accessed_at=datetime(2026, 5, 28, tzinfo=UTC),
        url="https://example.com/dividend",
        is_verified=verified,
    )


def evidence_section() -> models_dividends.DividendEvidenceSection:
    return models_dividends.DividendEvidenceSection(
        facts=[
            models_dividends.DividendEvidenceClaim(
                text="The issuer declared the dividend.",
                reference_ids=[SOURCE_ID],
            )
        ],
        data_gaps=[],
        reference_ids=[SOURCE_ID],
    )


def research() -> models_dividends.DividendResearch:
    section = evidence_section()
    return models_dividends.DividendResearch(
        dividend_terms=section,
        issuer_outlook=section,
        event_risks=section,
        market_context=section,
    )


def strategy(
    name: models_dividends.DividendStrategy,
    *,
    probability: float = 0.7,
    confidence: int = 75,
    profit_minimum: float = 2.0,
    eligibility: models_dividends.DividendStrategyEligibility = "Eligible",
) -> models_dividends.DividendStrategyAssessment:
    if eligibility != "Eligible":
        return models_dividends.DividendStrategyAssessment(
            strategy=name,
            eligibility=eligibility,
            ineligibility_reason="The strategy is not currently actionable.",
            success_probability=None,
            expected_entry_price=None,
            expected_exit_price=None,
            expected_profit_loss_per_share=None,
            break_even_price=None,
            recovery_days=None,
            confidence=confidence,
            risk=50,
            rationale="The strategy cannot be assessed as eligible.",
            risk_factors=[],
            assumptions=[],
            data_gaps=["Required estimates are unavailable."],
            reference_ids=[SOURCE_ID],
        )

    entry = numeric_range(100.0) if name == "DividendCapture" else numeric_range(98.0)
    return models_dividends.DividendStrategyAssessment(
        strategy=name,
        eligibility="Eligible",
        ineligibility_reason=None,
        success_probability=probability,
        expected_entry_price=entry,
        expected_exit_price=numeric_range(100.0, 101.0),
        expected_profit_loss_per_share=numeric_range(profit_minimum, profit_minimum + 1.0),
        break_even_price=numeric_range(98.0),
        recovery_days=models_dividends.DividendDayRange(minimum=1, maximum=3),
        confidence=confidence,
        risk=35,
        rationale="Historical recovery and current evidence support this estimate.",
        risk_factors=["Market volatility."],
        assumptions=[],
        data_gaps=[],
        reference_ids=[SOURCE_ID],
    )


def complete_analysis() -> models_dividends.DividendEventAnalysis:
    context = event_context()
    return models_dividends.DividendEventAnalysis(
        as_of=datetime(2026, 5, 28, tzinfo=UTC),
        analysis_status="Complete",
        failure_reason=None,
        overall_data_quality="High",
        event=context,
        historical_baseline=historical_baseline(),
        research=research(),
        evidence_adjusted_ex_date_close_drop=drop_estimate(),
        evidence_adjusted_pre_ex_close_recovery=recovery_estimate(numeric_range(100.0)),
        evidence_adjusted_capture_break_even_recovery=recovery_estimate(numeric_range(98.0)),
        evidence_adjusted_discount_break_even_recovery=recovery_estimate(numeric_range(98.0), probability=0.55),
        dividend_capture=strategy("DividendCapture"),
        post_dividend_discount=strategy("PostDividendDiscount", probability=0.55),
        recommendation=models_dividends.DividendRecommendation(
            outcome="DividendCapture",
            probability_advantage=0.15,
            rationale="Dividend capture has a material probability advantage.",
            reference_ids=[SOURCE_ID],
        ),
        validation_warnings=[],
        references=[reference()],
    )


def failed_analysis() -> models_dividends.DividendEventAnalysis:
    return models_dividends.DividendEventAnalysis(
        as_of=datetime(2026, 5, 28, tzinfo=UTC),
        analysis_status="Failed",
        failure_reason="Dividend research failed",
        overall_data_quality="Insufficient",
        event=event_context(),
        historical_baseline=historical_baseline(),
        research=None,
        evidence_adjusted_ex_date_close_drop=None,
        evidence_adjusted_pre_ex_close_recovery=None,
        evidence_adjusted_capture_break_even_recovery=None,
        evidence_adjusted_discount_break_even_recovery=None,
        dividend_capture=None,
        post_dividend_discount=None,
        recommendation=None,
        validation_warnings=[],
        references=[],
    )
