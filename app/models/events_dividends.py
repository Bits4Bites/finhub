from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from typing import Annotated, Literal, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, model_validator

from ..utils import ai_reference as ai_reference_utils
from . import ai as models_ai
from . import types as models_types

DividendEventPhase = Literal["BeforeExDate", "ExDate", "PostExDate", "Historical"]
DividendAnalysisStatus = Literal["Complete", "CompleteWithWarnings", "Failed"]
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
    """Round-trip transaction costs for each dividend-event strategy."""

    dividend_capture_per_share: float = Field(
        default=0.0,
        ge=0,
        allow_inf_nan=False,
        description="Round-trip transaction cost per share for dividend capture.",
    )
    post_dividend_discount_per_share: float = Field(
        default=0.0,
        ge=0,
        allow_inf_nan=False,
        description="Round-trip transaction cost per share for post-dividend discount entry.",
    )


class DividendNumericRange(models_ai.StrictAIModel):
    """Inclusive lower and upper bounds for a numeric estimate."""

    minimum: float = Field(
        allow_inf_nan=False,
        description="Lower bound of the estimated range.",
    )
    maximum: float = Field(
        allow_inf_nan=False,
        description="Upper bound of the estimated range.",
    )

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        if self.minimum > self.maximum:
            raise ValueError("minimum must not exceed maximum")
        return self


class DividendDayRange(models_ai.StrictAIModel):
    """Inclusive lower and upper bounds for an elapsed-day estimate."""

    minimum: int = Field(ge=0, description="Minimum estimated number of calendar days.")
    maximum: int = Field(ge=0, description="Maximum estimated number of calendar days.")

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        if self.minimum > self.maximum:
            raise ValueError("minimum must not exceed maximum")
        return self


class DividendDropEstimate(models_ai.StrictAIModel):
    """Estimated price decline for a dividend-event measurement point."""

    drop_amount: DividendNumericRange = Field(description="Estimated absolute price-decline range.")
    drop_percent: DividendNumericRange = Field(description="Estimated percentage price-decline range.")
    drop_to_dividend_ratio: DividendNumericRange = Field(
        description="Estimated price decline divided by the dividend amount."
    )
    estimated_price: DividendNumericRange = Field(description="Estimated resulting security-price range.")

    @model_validator(mode="after")
    def validate_prices(self) -> Self:
        if self.estimated_price.minimum < 0:
            raise ValueError("estimated prices must be non-negative")
        return self


class DividendRecoveryEstimate(models_ai.StrictAIModel):
    """Probability and timing estimate for reaching a target price."""

    target_price: DividendNumericRange = Field(description="Target price range that defines recovery.")
    success_probability: float = Field(
        ge=0,
        le=1,
        allow_inf_nan=False,
        description="Estimated probability of reaching the target within the analysis window.",
    )
    days: DividendDayRange | None = Field(
        description="Estimated calendar days to recovery, or null when recovery is not expected."
    )
    estimated_date_min: date | None = Field(
        description="Earliest estimated recovery date, or null without a recovery estimate."
    )
    estimated_date_max: date | None = Field(
        description="Latest estimated recovery date, or null without a recovery estimate."
    )

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
    """Deterministic market and technical indicators used by dividend analysis."""

    beta: float | None = Field(
        allow_inf_nan=False,
        description="Security beta, or null when unavailable.",
    )
    rsi14: float | None = Field(
        ge=0,
        le=100,
        allow_inf_nan=False,
        description="Fourteen-period relative strength index, or null when unavailable.",
    )
    average_daily_value_traded_7d: float | None = Field(
        ge=0,
        allow_inf_nan=False,
        description="Average daily value traded over seven trading days.",
    )
    average_volume_30d: float | None = Field(
        ge=0,
        allow_inf_nan=False,
        description="Average daily volume over 30 trading days.",
    )
    daily_return_volatility_30d: float | None = Field(
        ge=0,
        allow_inf_nan=False,
        description="Standard deviation of daily returns over 30 trading days.",
    )
    bid_ask_spread: float | None = Field(
        ge=0,
        allow_inf_nan=False,
        description="Observed bid-ask spread, or null when unavailable.",
    )
    stock_trend_60d: float | None = Field(
        allow_inf_nan=False,
        description="Security return trend over 60 trading days.",
    )
    market_trend_60d: float | None = Field(
        allow_inf_nan=False,
        description="Relevant broad-market return trend over 60 trading days.",
    )
    peer_trend_60d: float | None = Field(
        allow_inf_nan=False,
        description="Relevant peer-group return trend over 60 trading days.",
    )


class DividendEventContext(models_ai.StrictAIModel):
    """Verified security and event inputs for dividend analysis."""

    symbol: models_types.NonEmptyString = Field(
        max_length=4000,
        description="Canonical security symbol.",
    )
    exchange: models_types.NonEmptyString = Field(
        max_length=4000,
        description="Normalized exchange code.",
    )
    company_name: str | None = Field(description="Company or issuer name, or null when unavailable.")
    currency: models_types.NonEmptyString = Field(
        max_length=4000,
        description="Trading currency of prices and dividend amounts.",
    )
    country: str | None = Field(description="ISO market country code, or null when unavailable.")
    asset_type: models_types.NonEmptyString = Field(
        max_length=4000,
        description="Detected security or fund asset type.",
    )
    exchange_timezone: models_types.NonEmptyString = Field(
        max_length=4000,
        description="IANA timezone used for exchange-local event timing.",
    )
    ex_date: date = Field(description="Ex-dividend date.")
    phase: DividendEventPhase = Field(
        description="Lifecycle phase derived from the ex-dividend date and analysis time."
    )
    as_of: datetime = Field(description="Timezone-aware timestamp of the verified event context.")
    reference_price: float = Field(
        gt=0,
        allow_inf_nan=False,
        description="Verified price used as the baseline for estimates.",
    )
    dividend_amount: float = Field(
        gt=0,
        allow_inf_nan=False,
        description="Gross cash dividend per share.",
    )
    gross_dividend_yield: float = Field(
        ge=0,
        allow_inf_nan=False,
        description="Gross dividend amount divided by the reference price.",
    )
    holding_period_days: int = Field(
        ge=1,
        le=365,
        description="Calendar-day window used for recovery and strategy estimates.",
    )
    transaction_costs: DividendTransactionCosts = Field(
        description="Round-trip per-share costs used in strategy calculations."
    )

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
    """Deterministic historical and technical baseline for a dividend event."""

    sample_count: int = Field(
        ge=1,
        description="Number of comparable historical ex-dividend events.",
    )
    sample_quality: DividendSampleQuality = Field(description="Whether the historical sample is sufficient or limited.")
    quality_flags: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(
        max_length=20,
        description="Limitations or caveats affecting the historical sample.",
    )
    ex_date_open_drop: DividendDropEstimate = Field(description="Historical price-drop estimate at the ex-date open.")
    ex_date_close_drop: DividendDropEstimate = Field(description="Historical price-drop estimate at the ex-date close.")
    ex_date_intraday_low_drop: DividendDropEstimate = Field(
        description="Historical price-drop estimate at the ex-date intraday low."
    )
    post_ex_date_drawdown: DividendDropEstimate = Field(
        description="Historical maximum drawdown estimate after the ex-date."
    )
    pre_ex_close_recovery: DividendRecoveryEstimate = Field(
        description="Historical recovery estimate to the pre-ex-date close."
    )
    dividend_capture_break_even_recovery: DividendRecoveryEstimate = Field(
        description="Historical recovery estimate to dividend-capture break-even."
    )
    post_dividend_discount_break_even_recovery: DividendRecoveryEstimate = Field(
        description="Historical recovery estimate to post-dividend-discount break-even."
    )
    technical_context: DividendTechnicalContext = Field(
        description="Market and technical indicators measured for the event."
    )


class DividendEvidenceClaim(models_ai.StrictAIModel):
    """One externally sourced factual claim used in dividend analysis."""

    text: models_types.NonEmptyString = Field(
        max_length=4000,
        description="Factual evidence statement.",
    )
    reference_ids: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(
        min_length=1,
        max_length=6,
        description="Identifiers of sources supporting the claim.",
    )


class DividendEvidenceSection(models_ai.StrictAIModel):
    """A bounded group of sourced facts and known evidence gaps."""

    facts: list[DividendEvidenceClaim] = Field(
        max_length=3,
        description="Sourced facts relevant to this research topic.",
    )
    data_gaps: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(
        max_length=20,
        description="Missing, unavailable, or conflicting evidence for this topic.",
    )
    reference_ids: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(
        min_length=1,
        max_length=6,
        description="Identifiers of all sources used by this section.",
    )


class DividendResearch(models_ai.StrictAIModel):
    """Validated sourced research grouped by dividend-analysis topic."""

    dividend_terms: DividendEvidenceSection = Field(description="Evidence about the announced dividend terms.")
    issuer_outlook: DividendEvidenceSection = Field(description="Evidence about issuer performance and outlook.")
    event_risks: DividendEvidenceSection = Field(description="Evidence about risks specific to the dividend event.")
    market_context: DividendEvidenceSection = Field(
        description="Evidence about relevant market, sector, and macro conditions."
    )


class DividendStrategyAssessment(models_ai.StrictAIModel):
    """Structured assessment of one dividend-event trading strategy."""

    strategy: DividendStrategy = Field(description="Dividend-event strategy being assessed.")
    eligibility: DividendStrategyEligibility = Field(
        description="Whether available timing and evidence support assessing the strategy."
    )
    ineligibility_reason: models_types.NonEmptyString | None = Field(
        max_length=4000,
        description="Reason the strategy cannot be assessed, or null when eligible.",
    )
    success_probability: float | None = Field(
        default=None,
        ge=0,
        le=1,
        allow_inf_nan=False,
        description="Estimated probability of strategy success, or null when ineligible.",
    )
    expected_entry_price: DividendNumericRange | None = Field(
        description="Estimated entry-price range, or null when ineligible."
    )
    expected_exit_price: DividendNumericRange | None = Field(
        description="Estimated exit-price range, or null when ineligible."
    )
    expected_profit_loss_per_share: DividendNumericRange | None = Field(
        description="Estimated profit-or-loss range per share, or null when ineligible."
    )
    break_even_price: DividendNumericRange | None = Field(
        description="Estimated break-even price range, or null when ineligible."
    )
    recovery_days: DividendDayRange | None = Field(
        description="Estimated recovery-time range, or null when unavailable."
    )
    confidence: int = Field(
        ge=0,
        le=100,
        description="Confidence score for the assessment from zero through 100.",
    )
    risk: int = Field(
        ge=0,
        le=100,
        description="Risk score for the strategy from zero through 100.",
    )
    rationale: models_types.NonEmptyString = Field(
        max_length=4000,
        description="Evidence-based explanation of the strategy assessment.",
    )
    risk_factors: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(
        max_length=20,
        description="Material factors that could impair the strategy outcome.",
    )
    assumptions: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(
        max_length=20,
        description="Assumptions used to derive strategy estimates.",
    )
    data_gaps: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(
        max_length=20,
        description="Missing or uncertain information affecting the assessment.",
    )
    reference_ids: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(
        min_length=1,
        max_length=6,
        description="Identifiers of sources supporting the assessment.",
    )

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
    """Comparison outcome across the assessed dividend-event strategies."""

    outcome: DividendRecommendationOutcome = Field(
        description="Preferred strategy or the reason no strategy is preferred."
    )
    probability_advantage: float | None = Field(
        default=None,
        ge=0,
        le=1,
        allow_inf_nan=False,
        description="Absolute success-probability advantage of the preferred strategy.",
    )
    rationale: models_types.NonEmptyString = Field(
        max_length=4000,
        description="Evidence-based explanation of the comparison outcome.",
    )
    reference_ids: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(
        min_length=1,
        max_length=6,
        description="Identifiers of sources supporting the recommendation.",
    )


class DividendEventAnalysis(models_ai.StrictAIModel):
    """Final structured analysis of a dividend event and two trading strategies."""

    as_of: datetime = Field(description="Timezone-aware timestamp when analysis was finalized.")
    analysis_status: DividendAnalysisStatus = Field(description="Completion state of the dividend-event analysis.")
    failure_reason: str | None = Field(description="Failure detail when analysis_status is Failed; otherwise null.")
    overall_data_quality: models_types.DataQuality = Field(
        description="Overall quality of historical and researched evidence."
    )
    event: DividendEventContext = Field(description="Verified security and dividend-event context.")
    historical_baseline: DividendHistoricalBaseline = Field(
        description="Deterministic historical and technical baseline."
    )
    research: DividendResearch | None = Field(description="Validated sourced research, or null when research failed.")
    evidence_adjusted_ex_date_close_drop: DividendDropEstimate | None = Field(
        description="Research-adjusted ex-date close-drop estimate, or null on failure."
    )
    evidence_adjusted_pre_ex_close_recovery: DividendRecoveryEstimate | None = Field(
        description="Research-adjusted recovery estimate to the pre-ex close."
    )
    evidence_adjusted_capture_break_even_recovery: DividendRecoveryEstimate | None = Field(
        description="Research-adjusted recovery estimate to capture break-even."
    )
    evidence_adjusted_discount_break_even_recovery: DividendRecoveryEstimate | None = Field(
        description="Research-adjusted recovery estimate to discount-entry break-even."
    )
    dividend_capture: DividendStrategyAssessment | None = Field(
        description="Dividend-capture strategy assessment, or null on failure."
    )
    post_dividend_discount: DividendStrategyAssessment | None = Field(
        description="Post-dividend-discount strategy assessment, or null on failure."
    )
    recommendation: DividendRecommendation | None = Field(
        description="Comparison outcome across strategies, or null on failure."
    )
    validation_warnings: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(
        max_length=20,
        description="Application corrections or validation caveats applied to AI output.",
    )
    references: list[models_ai.ReferenceSource] = Field(
        max_length=6,
        description="Canonical sources cited by research and assessment.",
    )

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
