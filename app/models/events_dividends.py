from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from typing import Annotated, Literal, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, model_validator

from ..utils import ai_reference as ai_reference_utils
from . import ai as models_ai

NonEmptyString = Annotated[str, Field(min_length=1, max_length=4000)]
DividendEventPhase = Literal["BeforeExDate", "ExDate", "PostExDate", "Historical"]
DividendAnalysisStatus = Literal["Complete", "CompleteWithWarnings", "Failed"]
DividendDataQuality = Literal["High", "Medium", "Low", "Insufficient"]
DividendSampleQuality = Literal["Sufficient", "Limited"]
DividendStrategy = Literal["DividendCapture", "PostDividendDiscount"]
DividendStrategyEligibility = Literal["Eligible", "Ineligible", "InsufficientData"]
DividendRecommendationOutcome = Literal[
    "DividendCapture",
    "PostDividendDiscount",
    "NoClearWinner",
    "InsufficientInsights",
]


class DividendTransactionCosts(models_ai.StrictAIModel):
    dividend_capture_per_share: float = Field(default=0.0, ge=0, allow_inf_nan=False)
    post_dividend_discount_per_share: float = Field(default=0.0, ge=0, allow_inf_nan=False)


class DividendNumericRange(models_ai.StrictAIModel):
    minimum: float = Field(allow_inf_nan=False)
    maximum: float = Field(allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        if self.minimum > self.maximum:
            raise ValueError("minimum must not exceed maximum")
        return self


class DividendDayRange(models_ai.StrictAIModel):
    minimum: int = Field(ge=0)
    maximum: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        if self.minimum > self.maximum:
            raise ValueError("minimum must not exceed maximum")
        return self


class DividendDropEstimate(models_ai.StrictAIModel):
    drop_amount: DividendNumericRange
    drop_percent: DividendNumericRange
    drop_to_dividend_ratio: DividendNumericRange
    estimated_price: DividendNumericRange

    @model_validator(mode="after")
    def validate_prices(self) -> Self:
        if self.estimated_price.minimum < 0:
            raise ValueError("estimated prices must be non-negative")
        return self


class DividendRecoveryEstimate(models_ai.StrictAIModel):
    target_price: DividendNumericRange
    success_probability: float = Field(ge=0, le=1, allow_inf_nan=False)
    days: DividendDayRange | None
    estimated_date_min: date | None
    estimated_date_max: date | None

    @model_validator(mode="after")
    def validate_dates(self) -> Self:
        if self.target_price.minimum < 0:
            raise ValueError("recovery target prices must be non-negative")
        if (self.estimated_date_min is None) != (self.estimated_date_max is None):
            raise ValueError("estimated recovery dates must both be present or absent")
        if (
            self.estimated_date_min is not None
            and self.estimated_date_max is not None
            and self.estimated_date_min > self.estimated_date_max
        ):
            raise ValueError("estimated_date_min must not exceed estimated_date_max")
        if (self.days is None) != (self.estimated_date_min is None):
            raise ValueError("recovery days and estimated dates must both be present or absent")
        if self.success_probability == 0 and self.days is not None:
            raise ValueError("zero recovery probability cannot have a recovery range")
        if self.success_probability > 0 and self.days is None:
            raise ValueError("positive recovery probability requires a recovery range")
        return self


class DividendTechnicalContext(models_ai.StrictAIModel):
    beta: float | None = Field(allow_inf_nan=False)
    rsi14: float | None = Field(ge=0, le=100, allow_inf_nan=False)
    average_daily_value_traded_7d: float | None = Field(ge=0, allow_inf_nan=False)
    average_volume_30d: float | None = Field(ge=0, allow_inf_nan=False)
    daily_return_volatility_30d: float | None = Field(ge=0, allow_inf_nan=False)
    bid_ask_spread: float | None = Field(ge=0, allow_inf_nan=False)
    stock_trend_60d: float | None = Field(allow_inf_nan=False)
    market_trend_60d: float | None = Field(allow_inf_nan=False)
    peer_trend_60d: float | None = Field(allow_inf_nan=False)


class DividendEventContext(models_ai.StrictAIModel):
    symbol: NonEmptyString
    exchange: NonEmptyString
    company_name: str | None
    currency: NonEmptyString
    country: str | None
    asset_type: NonEmptyString
    exchange_timezone: NonEmptyString
    ex_date: date
    phase: DividendEventPhase
    as_of: datetime
    reference_price: float = Field(gt=0, allow_inf_nan=False)
    dividend_amount: float = Field(gt=0, allow_inf_nan=False)
    gross_dividend_yield: float = Field(ge=0, allow_inf_nan=False)
    holding_period_days: int = Field(ge=1, le=365)
    transaction_costs: DividendTransactionCosts

    @model_validator(mode="after")
    def validate_phase(self) -> Self:
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("event as_of must be timezone-aware")
        try:
            local_date = self.as_of.astimezone(ZoneInfo(self.exchange_timezone)).date()
        except ZoneInfoNotFoundError as exc:
            raise ValueError("exchange_timezone must be a valid timezone") from exc
        if self.ex_date > local_date:
            expected_phase: DividendEventPhase = "BeforeExDate"
        elif self.ex_date == local_date:
            expected_phase = "ExDate"
        elif self.ex_date + timedelta(days=self.holding_period_days) >= local_date:
            expected_phase = "PostExDate"
        else:
            expected_phase = "Historical"
        if self.phase != expected_phase:
            raise ValueError("event phase is inconsistent with ex_date and exchange-local as_of")
        return self


class DividendHistoricalBaseline(models_ai.StrictAIModel):
    sample_count: int = Field(ge=1)
    sample_quality: DividendSampleQuality
    quality_flags: list[NonEmptyString] = Field(max_length=20)
    ex_date_open_drop: DividendDropEstimate
    ex_date_close_drop: DividendDropEstimate
    ex_date_intraday_low_drop: DividendDropEstimate
    post_ex_date_drawdown: DividendDropEstimate
    pre_ex_close_recovery: DividendRecoveryEstimate
    dividend_capture_break_even_recovery: DividendRecoveryEstimate
    post_dividend_discount_break_even_recovery: DividendRecoveryEstimate
    technical_context: DividendTechnicalContext


class DividendEvidenceClaim(models_ai.StrictAIModel):
    text: NonEmptyString
    reference_ids: list[NonEmptyString] = Field(min_length=1, max_length=6)


class DividendEvidenceSection(models_ai.StrictAIModel):
    facts: list[DividendEvidenceClaim] = Field(max_length=3)
    data_gaps: list[NonEmptyString] = Field(max_length=20)
    reference_ids: list[NonEmptyString] = Field(min_length=1, max_length=6)


class DividendResearch(models_ai.StrictAIModel):
    dividend_terms: DividendEvidenceSection
    issuer_outlook: DividendEvidenceSection
    event_risks: DividendEvidenceSection
    market_context: DividendEvidenceSection


class DividendStrategyAssessment(models_ai.StrictAIModel):
    strategy: DividendStrategy
    eligibility: DividendStrategyEligibility
    ineligibility_reason: NonEmptyString | None
    success_probability: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    expected_entry_price: DividendNumericRange | None
    expected_exit_price: DividendNumericRange | None
    expected_profit_loss_per_share: DividendNumericRange | None
    break_even_price: DividendNumericRange | None
    recovery_days: DividendDayRange | None
    confidence: int = Field(ge=0, le=100)
    risk: int = Field(ge=0, le=100)
    rationale: NonEmptyString
    risk_factors: list[NonEmptyString] = Field(max_length=20)
    assumptions: list[NonEmptyString] = Field(max_length=20)
    data_gaps: list[NonEmptyString] = Field(max_length=20)
    reference_ids: list[NonEmptyString] = Field(min_length=1, max_length=6)

    @model_validator(mode="after")
    def validate_eligibility(self) -> Self:
        price_ranges = (
            self.expected_entry_price,
            self.expected_exit_price,
            self.break_even_price,
        )
        if any(price_range is not None and price_range.minimum < 0 for price_range in price_ranges):
            raise ValueError("strategy prices must be non-negative")
        if self.eligibility == "Eligible":
            required_values = (
                self.success_probability,
                self.expected_entry_price,
                self.expected_exit_price,
                self.expected_profit_loss_per_share,
                self.break_even_price,
            )
            if any(value is None for value in required_values):
                raise ValueError("eligible strategy assessments require complete estimates")
            if self.success_probability == 0 and self.recovery_days is not None:
                raise ValueError("zero success probability cannot have a recovery range")
            if self.success_probability is not None and self.success_probability > 0 and self.recovery_days is None:
                raise ValueError("positive success probability requires a recovery range")
            if self.ineligibility_reason is not None:
                raise ValueError("eligible strategy assessments cannot have an ineligibility reason")
        else:
            if not self.ineligibility_reason:
                raise ValueError("non-eligible strategy assessments require an ineligibility reason")
            estimates = (
                self.success_probability,
                self.expected_entry_price,
                self.expected_exit_price,
                self.expected_profit_loss_per_share,
                self.break_even_price,
                self.recovery_days,
            )
            if any(value is not None for value in estimates):
                raise ValueError("non-eligible strategy assessments cannot contain estimates")
        return self


class DividendRecommendation(models_ai.StrictAIModel):
    outcome: DividendRecommendationOutcome
    probability_advantage: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    rationale: NonEmptyString
    reference_ids: list[NonEmptyString] = Field(min_length=1, max_length=6)


class DividendEventAnalysis(models_ai.StrictAIModel):
    as_of: datetime
    analysis_status: DividendAnalysisStatus
    failure_reason: str | None
    overall_data_quality: DividendDataQuality
    event: DividendEventContext
    historical_baseline: DividendHistoricalBaseline
    research: DividendResearch | None
    evidence_adjusted_ex_date_close_drop: DividendDropEstimate | None
    evidence_adjusted_pre_ex_close_recovery: DividendRecoveryEstimate | None
    evidence_adjusted_capture_break_even_recovery: DividendRecoveryEstimate | None
    evidence_adjusted_discount_break_even_recovery: DividendRecoveryEstimate | None
    dividend_capture: DividendStrategyAssessment | None
    post_dividend_discount: DividendStrategyAssessment | None
    recommendation: DividendRecommendation | None
    validation_warnings: list[NonEmptyString] = Field(max_length=20)
    references: list[models_ai.ReferenceSource] = Field(max_length=6)

    @model_validator(mode="after")
    def validate_analysis(self) -> Self:
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("analysis as_of must be timezone-aware")
        if self.analysis_status != "Failed":
            if self.failure_reason is not None:
                raise ValueError("complete analysis cannot have a failure reason")
            required_ai_fields = (
                self.research,
                self.dividend_capture,
                self.post_dividend_discount,
                self.recommendation,
            )
            if any(value is None for value in required_ai_fields) or not self.references:
                raise ValueError("complete analysis requires research, strategies, recommendation, and references")
            if self.analysis_status == "Complete" and self.validation_warnings:
                raise ValueError("complete analysis cannot have validation warnings")
            if self.analysis_status == "CompleteWithWarnings" and not self.validation_warnings:
                raise ValueError("CompleteWithWarnings analysis requires validation warnings")
        else:
            if not self.failure_reason:
                raise ValueError("failed analysis requires a failure reason")
            if self.validation_warnings:
                raise ValueError("failed analysis cannot have validation warnings")
            if any(
                value is not None
                for value in (
                    self.evidence_adjusted_ex_date_close_drop,
                    self.evidence_adjusted_pre_ex_close_recovery,
                    self.evidence_adjusted_capture_break_even_recovery,
                    self.evidence_adjusted_discount_break_even_recovery,
                    self.dividend_capture,
                    self.post_dividend_discount,
                    self.recommendation,
                )
            ):
                raise ValueError("failed analysis cannot contain assessment results")
            if self.research is None and self.references:
                raise ValueError("failed analysis without research cannot contain references")

        if self.references:
            ai_reference_utils.validate_reference_registry(self.references, self)
        if self.dividend_capture is None or self.post_dividend_discount is None:
            return self
        if self.dividend_capture.strategy != "DividendCapture":
            raise ValueError("dividend_capture must assess DividendCapture")
        if self.post_dividend_discount.strategy != "PostDividendDiscount":
            raise ValueError("post_dividend_discount must assess PostDividendDiscount")
        if self.event.phase != "BeforeExDate" and self.dividend_capture.eligibility == "Eligible":
            raise ValueError("DividendCapture is ineligible on or after the ex-dividend date")
        if not math.isfinite(self.event.reference_price):
            raise ValueError("reference_price must be finite")
        return self
