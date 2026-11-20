from __future__ import annotations

import datetime
import math
import typing
import zoneinfo

import pydantic

from ..utils import ai_reference as ai_reference_utils
from ..utils import conv
from . import ai as models_ai
from . import events_base
from . import portfolio as models_portfolio
from . import types as models_types

DividendEventPhase = typing.Literal["BeforeExDate", "ExDate", "PostExDate", "Historical"]
DividendAnalysisStatus = typing.Literal["Complete", "CompleteWithWarnings", "Failed"]
DividendSampleQuality = typing.Literal["Sufficient", "Limited"]
DividendStrategy = typing.Literal["DividendCapture", "PostDividendDiscount"]
DividendStrategyEligibility = typing.Literal["Eligible", "Ineligible", "InsufficientData"]
DividendRecommendationOutcome = typing.Literal[
    "DividendCapture",
    "PostDividendDiscount",
    "NoClearWinner",
    "InsufficientInsights",
]


_DIVIDEND_EVENT_FIELDS = {
    "sym": "symbol",
    "exchange": "exchange",
    "corp": "company_name",
    "date": "timestamp_str",
    "pdate": "payment_date",
    "cat": "event_category",
    "src": "source_name",
    "link": "link",
    "status": "status",
    "amount": "amount",
    "yield": "dividend_yield",
    "currency": "currency",
}


class DividendEventMetrics(events_base.EventBase):
    """Legacy dividend-event metrics and AI assessment attached to an event."""

    price: float = pydantic.Field(default=0.0, description="Current security price.")
    div_amount: float = pydantic.Field(default=0.0, description="Dividend amount per share.")
    div_yield: float = pydantic.Field(
        default=0.0,
        description="Caller-supplied dividend amount-to-price ratio; this legacy model does not recompute it.",
    )
    num_samples: int = pydantic.Field(
        default=0,
        description="Number of historical dividend events used for analysis.",
    )
    drop_price_min: float = pydantic.Field(
        default=0.0,
        description="Lower historical estimate of the ex-dividend price drop.",
    )
    drop_price_max: float = pydantic.Field(
        default=0.0,
        description="Upper historical estimate of the ex-dividend price drop.",
    )
    recovery_probability: float = pydantic.Field(
        default=0.0,
        description="Estimated probability of recovering the reference price.",
    )
    recovery_days_min: int = pydantic.Field(
        default=0,
        description="Lower estimate of calendar days to price recovery.",
    )
    recovery_days_max: int = pydantic.Field(
        default=0,
        description="Upper estimate of calendar days to price recovery.",
    )
    recovery_price_min: float = pydantic.Field(
        default=0.0,
        description="Lower price estimate for recovery.",
    )
    recovery_price_max: float = pydantic.Field(
        default=0.0,
        description="Upper price estimate for recovery.",
    )
    beta: float = pydantic.Field(default=0.0, description="Security beta used as market-sensitivity context.")
    rsi14: int = pydantic.Field(default=0, description="Fourteen-period relative strength index.")
    avg_dvt_7d: int = pydantic.Field(
        default=0,
        description="Average daily value traded over seven trading days.",
    )
    std_dvt_7d: int = pydantic.Field(
        default=0,
        description="Standard deviation of daily value traded over seven trading days.",
    )
    avg_volume_30d: int = pydantic.Field(
        default=0,
        description="Average daily volume over 30 trading days.",
    )
    std_volume_30d: int = pydantic.Field(
        default=0,
        description="Standard deviation of daily volume over 30 trading days.",
    )
    bid_ask_spread: float = pydantic.Field(default=0.0, description="Observed bid-ask spread.")
    trend_60d: float = pydantic.Field(
        default=0.0,
        description="Security price trend over 60 trading days.",
    )
    market_trend_60d: float = pydantic.Field(
        default=0.0,
        description="Relevant market trend over 60 trading days.",
    )
    peer_trend_60d: float = pydantic.Field(
        default=0.0,
        description="Relevant peer-group trend over 60 trading days.",
    )


class UpcomingDividendEvent(events_base.EventBase):
    """An announced upcoming dividend or distribution event."""

    status: str = pydantic.Field(default="", description="Source-reported event status.")
    amount: float = pydantic.Field(default=0.0, description="Announced dividend amount per share.")
    dividend_yield: float = pydantic.Field(
        default=0.0,
        description="Announced or derived dividend yield.",
    )
    currency: str = pydantic.Field(default="", description="Currency of the dividend amount.")
    payment_date: str | None = pydantic.Field(description="Scheduled payment date, when available.")
    analysis: DividendEventMetrics | None = pydantic.Field(
        default=None,
        description="Optional legacy analysis associated with the dividend event.",
    )


def parse_upcoming_dividend_events_from_json(
    json_str: str,
    default_vals: dict[str, typing.Any] | None = None,
) -> list[UpcomingDividendEvent]:
    """Build validated upcoming dividend events from source JSON.

    Args:
        json_str: A JSON array of event objects, optionally wrapped in a complete
            Markdown ``json`` fence. Objects use ``sym``, ``exchange``, ``corp``,
            ``date``, ``pdate``, ``cat``, ``src``, ``link``, ``status``,
            ``amount``, ``yield``, and ``currency`` source keys. ``date`` must
            use exactly ``YYYY-MM-DD``, including a zero-padded month and day.
        default_vals: Optional fallback values keyed by the same source names.
            A fallback applies only when its key is absent; an explicit JSON
            null is retained for final model validation.

    Returns:
        Events in input order, with parser-produced timestamps at midnight UTC
        on their source dates. An empty array returns an empty list. Missing
        values use model defaults where available, and a missing ``cat`` without
        a supplied fallback becomes ``"dividend"``.

    Raises:
        json.JSONDecodeError: If ``json_str`` is not valid JSON.
        ValueError: If the top-level JSON value is not an array, or a date is
            not a valid calendar date in exact ``YYYY-MM-DD`` form.
        TypeError: If an array item is not a JSON object.
        pydantic.ValidationError: If a record or explicit null does not satisfy
            the final event model.
    """
    defaults = default_vals or {}
    events = events_base._parse_event_records(json_str)
    result = []
    for item in events:
        event_values = events_base._event_values(item, defaults, _DIVIDEND_EVENT_FIELDS)
        event_values.setdefault("event_category", "dividend")
        event = UpcomingDividendEvent(**event_values)
        event.timestamp = events_base._event_date_timestamp(event.timestamp_str)
        result.append(event)

    return result


class DividendTransactionCosts(models_ai.StrictAIModel):
    """Round-trip transaction costs for each dividend-event strategy."""

    dividend_capture_per_share: float = pydantic.Field(
        default=0.0,
        ge=0,
        allow_inf_nan=False,
        description="Round-trip transaction cost per share for dividend capture.",
    )
    post_dividend_discount_per_share: float = pydantic.Field(
        default=0.0,
        ge=0,
        allow_inf_nan=False,
        description="Round-trip transaction cost per share for post-dividend discount entry.",
    )


class DividendNumericRange(models_ai.StrictAIModel):
    """Inclusive lower and upper bounds for a numeric estimate."""

    minimum: float = pydantic.Field(
        allow_inf_nan=False,
        description="Lower bound of the estimated range.",
    )
    maximum: float = pydantic.Field(
        allow_inf_nan=False,
        description="Upper bound of the estimated range.",
    )

    @pydantic.model_validator(mode="after")
    def validate_order(self) -> typing.Self:
        if self.minimum > self.maximum:
            raise ValueError("minimum must not exceed maximum")
        return self


class DividendDayRange(models_ai.StrictAIModel):
    """Inclusive lower and upper bounds for an elapsed-day estimate."""

    minimum: int = pydantic.Field(ge=0, description="Minimum estimated number of calendar days.")
    maximum: int = pydantic.Field(ge=0, description="Maximum estimated number of calendar days.")

    @pydantic.model_validator(mode="after")
    def validate_order(self) -> typing.Self:
        if self.minimum > self.maximum:
            raise ValueError("minimum must not exceed maximum")
        return self


class DividendDropEstimate(models_ai.StrictAIModel):
    """Estimated price decline for a dividend-event measurement point."""

    drop_amount: DividendNumericRange = pydantic.Field(description="Estimated absolute price-decline range.")
    drop_percent: DividendNumericRange = pydantic.Field(description="Estimated percentage price-decline range.")
    drop_to_dividend_ratio: DividendNumericRange = pydantic.Field(
        description="Estimated price decline divided by the dividend amount."
    )
    estimated_price: DividendNumericRange = pydantic.Field(description="Estimated resulting security-price range.")

    @pydantic.model_validator(mode="after")
    def validate_prices(self) -> typing.Self:
        if self.estimated_price.minimum < 0:
            raise ValueError("estimated prices must be non-negative")
        return self


class DividendRecoveryEstimate(models_ai.StrictAIModel):
    """Probability and timing estimate for reaching a target price.

    A positive recovery probability requires both a day range and estimated
    date range. Zero probability carries neither, and both estimated dates are
    present or absent together.
    """

    target_price: DividendNumericRange = pydantic.Field(description="Target price range that defines recovery.")
    success_probability: float = pydantic.Field(
        ge=0,
        le=1,
        allow_inf_nan=False,
        description="Estimated probability of reaching the target within the analysis window.",
    )
    days: DividendDayRange | None = pydantic.Field(
        description="Estimated calendar days to recovery, or null when recovery is not expected."
    )
    estimated_date_min: datetime.date | None = pydantic.Field(
        description="Earliest estimated recovery date, or null without a recovery estimate."
    )
    estimated_date_max: datetime.date | None = pydantic.Field(
        description="Latest estimated recovery date, or null without a recovery estimate."
    )

    @pydantic.model_validator(mode="after")
    def validate_dates(self) -> typing.Self:
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

    beta: float | None = pydantic.Field(
        allow_inf_nan=False,
        description="Security beta, or null when unavailable.",
    )
    rsi14: float | None = pydantic.Field(
        ge=0,
        le=100,
        allow_inf_nan=False,
        description="Fourteen-period relative strength index, or null when unavailable.",
    )
    average_daily_value_traded_7d: float | None = pydantic.Field(
        ge=0,
        allow_inf_nan=False,
        description="Average daily value traded over seven trading days.",
    )
    average_volume_30d: float | None = pydantic.Field(
        ge=0,
        allow_inf_nan=False,
        description="Average daily volume over 30 trading days.",
    )
    daily_return_volatility_30d: float | None = pydantic.Field(
        ge=0,
        allow_inf_nan=False,
        description="Standard deviation of daily returns over 30 trading days.",
    )
    bid_ask_spread: float | None = pydantic.Field(
        ge=0,
        allow_inf_nan=False,
        description="Observed bid-ask spread, or null when unavailable.",
    )
    stock_trend_60d: float | None = pydantic.Field(
        allow_inf_nan=False,
        description="Security return trend over 60 trading days.",
    )
    market_trend_60d: float | None = pydantic.Field(
        allow_inf_nan=False,
        description="Relevant broad-market return trend over 60 trading days.",
    )
    peer_trend_60d: float | None = pydantic.Field(
        allow_inf_nan=False,
        description="Relevant peer-group return trend over 60 trading days.",
    )


class DividendEventContext(models_ai.StrictAIModel):
    """Verified security and event inputs for dividend analysis.

    The symbol accepts Yahoo Finance or canonical EXCHANGE:CODE format. String
    identifiers are trimmed and uppercased where applicable. Gross dividend
    yield must equal dividend amount divided by reference price, and phase must
    match the exchange-local analysis date.
    """

    symbol: models_types.NonEmptyString = pydantic.Field(
        max_length=4000,
        description=(
            "Security symbol in Yahoo Finance or canonical EXCHANGE:CODE format; "
            "input is trimmed and uppercased, with exchange aliases canonicalized."
        ),
    )
    exchange: models_types.NonEmptyString = pydantic.Field(
        max_length=4000,
        description=(
            "Normalized exchange code; input is trimmed, uppercased, and recognized aliases are canonicalized."
        ),
    )
    company_name: str | None = pydantic.Field(description="Company or issuer name, or null when unavailable.")
    currency: models_types.CurrencyCode = pydantic.Field(
        description="Three-letter trading currency; input is trimmed and uppercased.",
    )
    country: str | None = pydantic.Field(
        description="Provider market country code or name, trimmed when supplied, or null when unavailable."
    )
    asset_type: models_types.NonEmptyString = pydantic.Field(
        max_length=4000,
        description="Detected security or fund asset type.",
    )
    exchange_timezone: models_types.NonEmptyString = pydantic.Field(
        max_length=4000,
        description="IANA timezone used for exchange-local event timing.",
    )
    ex_date: datetime.date = pydantic.Field(description="Ex-dividend date.")
    phase: DividendEventPhase = pydantic.Field(
        description="Lifecycle phase derived from the ex-dividend date and analysis time."
    )
    as_of: datetime.datetime = pydantic.Field(description="Timezone-aware timestamp of the verified event context.")
    reference_price: float = pydantic.Field(
        gt=0,
        allow_inf_nan=False,
        description="Verified price used as the baseline for estimates.",
    )
    dividend_amount: float = pydantic.Field(
        gt=0,
        allow_inf_nan=False,
        description="Gross cash dividend per share.",
    )
    gross_dividend_yield: float = pydantic.Field(
        ge=0,
        allow_inf_nan=False,
        description="Gross dividend amount divided by the reference price; validated by this model.",
    )
    holding_period_days: int = pydantic.Field(
        ge=1,
        le=365,
        description="Calendar-day window used for recovery and strategy estimates.",
    )
    transaction_costs: DividendTransactionCosts = pydantic.Field(
        description="Round-trip per-share costs used in strategy calculations."
    )

    @pydantic.field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip().upper()
        if any(character.isspace() for character in normalized):
            raise ValueError("symbol cannot contain whitespace")
        return models_portfolio.normalize_canonical_ticker(normalized) if ":" in normalized else normalized

    @pydantic.field_validator("exchange", mode="before")
    @classmethod
    def normalize_exchange(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = conv.normalize_exchange_code(value)
        if not normalized or ":" in normalized or any(character.isspace() for character in normalized):
            raise ValueError("exchange must be a nonblank code without whitespace")
        return normalized

    @pydantic.field_validator("country", mode="before")
    @classmethod
    def normalize_country(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        return normalized or None

    @pydantic.model_validator(mode="after")
    def validate_phase(self) -> typing.Self:
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("event as_of must be timezone-aware")
        if ":" in self.symbol and self.symbol.split(":", 1)[0] != self.exchange:
            raise ValueError("event exchange must match the canonical symbol")
        expected_yield = self.dividend_amount / self.reference_price
        if abs(self.gross_dividend_yield - expected_yield) > 1e-9:
            raise ValueError("gross_dividend_yield must match dividend amount and reference price")
        try:
            local_date = self.as_of.astimezone(zoneinfo.ZoneInfo(self.exchange_timezone)).date()
        except zoneinfo.ZoneInfoNotFoundError as exc:
            raise ValueError("exchange_timezone must be a valid timezone") from exc
        if self.ex_date > local_date:
            expected_phase: DividendEventPhase = "BeforeExDate"
        elif self.ex_date == local_date:
            expected_phase = "ExDate"
        elif self.ex_date + datetime.timedelta(days=self.holding_period_days) >= local_date:
            expected_phase = "PostExDate"
        else:
            expected_phase = "Historical"
        if self.phase != expected_phase:
            raise ValueError("event phase is inconsistent with ex_date and exchange-local as_of")
        return self


class DividendHistoricalBaseline(models_ai.StrictAIModel):
    """Deterministic historical and technical baseline for a dividend event."""

    sample_count: int = pydantic.Field(
        ge=1,
        description="Number of comparable historical ex-dividend events.",
    )
    sample_quality: DividendSampleQuality = pydantic.Field(
        description="Whether the historical sample is sufficient or limited."
    )
    quality_flags: list[typing.Annotated[models_types.NonEmptyString, pydantic.Field(max_length=4000)]] = (
        pydantic.Field(
            max_length=20,
            description="Limitations or caveats affecting the historical sample.",
        )
    )
    ex_date_open_drop: DividendDropEstimate = pydantic.Field(
        description="Historical price-drop estimate at the ex-date open."
    )
    ex_date_close_drop: DividendDropEstimate = pydantic.Field(
        description="Historical price-drop estimate at the ex-date close."
    )
    ex_date_intraday_low_drop: DividendDropEstimate = pydantic.Field(
        description="Historical price-drop estimate at the ex-date intraday low."
    )
    post_ex_date_drawdown: DividendDropEstimate = pydantic.Field(
        description="Historical maximum drawdown estimate after the ex-date."
    )
    pre_ex_close_recovery: DividendRecoveryEstimate = pydantic.Field(
        description="Historical recovery estimate to the pre-ex-date close."
    )
    dividend_capture_break_even_recovery: DividendRecoveryEstimate = pydantic.Field(
        description="Historical recovery estimate to dividend-capture break-even."
    )
    post_dividend_discount_break_even_recovery: DividendRecoveryEstimate = pydantic.Field(
        description="Historical recovery estimate to post-dividend-discount break-even."
    )
    technical_context: DividendTechnicalContext = pydantic.Field(
        description="Market and technical indicators measured for the event."
    )


class DividendEvidenceClaim(models_ai.StrictAIModel):
    """One externally sourced factual claim used in dividend analysis."""

    text: models_types.NonEmptyString = pydantic.Field(
        max_length=4000,
        description="Factual evidence statement.",
    )
    reference_ids: list[typing.Annotated[models_types.NonEmptyString, pydantic.Field(max_length=4000)]] = (
        pydantic.Field(
            min_length=1,
            max_length=6,
            description="Identifiers of sources supporting the claim.",
        )
    )


class DividendEvidenceSection(models_ai.StrictAIModel):
    """A bounded group of sourced facts and known evidence gaps."""

    facts: list[DividendEvidenceClaim] = pydantic.Field(
        max_length=3,
        description="Sourced facts relevant to this research topic.",
    )
    data_gaps: list[typing.Annotated[models_types.NonEmptyString, pydantic.Field(max_length=4000)]] = pydantic.Field(
        max_length=20,
        description="Missing, unavailable, or conflicting evidence for this topic.",
    )
    reference_ids: list[typing.Annotated[models_types.NonEmptyString, pydantic.Field(max_length=4000)]] = (
        pydantic.Field(
            min_length=1,
            max_length=6,
            description="Identifiers of all sources used by this section.",
        )
    )


class DividendResearch(models_ai.StrictAIModel):
    """Validated sourced research grouped by dividend-analysis topic."""

    dividend_terms: DividendEvidenceSection = pydantic.Field(description="Evidence about the announced dividend terms.")
    issuer_outlook: DividendEvidenceSection = pydantic.Field(
        description="Evidence about issuer performance and outlook."
    )
    event_risks: DividendEvidenceSection = pydantic.Field(
        description="Evidence about risks specific to the dividend event."
    )
    market_context: DividendEvidenceSection = pydantic.Field(
        description="Evidence about relevant market, sector, and macro conditions."
    )


class DividendStrategyAssessment(models_ai.StrictAIModel):
    """Structured assessment of one dividend-event trading strategy.

    Eligible strategies include complete price and probability estimates, with
    recovery days only when success probability is positive. Non-eligible
    strategies include a reason and no estimates.
    """

    strategy: DividendStrategy = pydantic.Field(description="Dividend-event strategy being assessed.")
    eligibility: DividendStrategyEligibility = pydantic.Field(
        description="Whether available timing and evidence support assessing the strategy."
    )
    ineligibility_reason: models_types.NonEmptyString | None = pydantic.Field(
        max_length=4000,
        description="Reason the strategy cannot be assessed, or null when eligible.",
    )
    success_probability: float | None = pydantic.Field(
        default=None,
        ge=0,
        le=1,
        allow_inf_nan=False,
        description="Estimated probability of strategy success, or null when ineligible.",
    )
    expected_entry_price: DividendNumericRange | None = pydantic.Field(
        description="Estimated entry-price range, or null when ineligible."
    )
    expected_exit_price: DividendNumericRange | None = pydantic.Field(
        description="Estimated exit-price range, or null when ineligible."
    )
    expected_profit_loss_per_share: DividendNumericRange | None = pydantic.Field(
        description="Estimated profit-or-loss range per share, or null when ineligible."
    )
    break_even_price: DividendNumericRange | None = pydantic.Field(
        description="Estimated break-even price range, or null when ineligible."
    )
    recovery_days: DividendDayRange | None = pydantic.Field(
        description="Estimated recovery-time range, or null when unavailable."
    )
    confidence: int = pydantic.Field(
        ge=0,
        le=100,
        description="Confidence score for the assessment from zero through 100.",
    )
    risk: int = pydantic.Field(
        ge=0,
        le=100,
        description="Risk score for the strategy from zero through 100.",
    )
    rationale: models_types.NonEmptyString = pydantic.Field(
        max_length=4000,
        description="Evidence-based explanation of the strategy assessment.",
    )
    risk_factors: list[typing.Annotated[models_types.NonEmptyString, pydantic.Field(max_length=4000)]] = pydantic.Field(
        max_length=20,
        description="Material factors that could impair the strategy outcome.",
    )
    assumptions: list[typing.Annotated[models_types.NonEmptyString, pydantic.Field(max_length=4000)]] = pydantic.Field(
        max_length=20,
        description="Assumptions used to derive strategy estimates.",
    )
    data_gaps: list[typing.Annotated[models_types.NonEmptyString, pydantic.Field(max_length=4000)]] = pydantic.Field(
        max_length=20,
        description="Missing or uncertain information affecting the assessment.",
    )
    reference_ids: list[typing.Annotated[models_types.NonEmptyString, pydantic.Field(max_length=4000)]] = (
        pydantic.Field(
            min_length=1,
            max_length=6,
            description="Identifiers of sources supporting the assessment.",
        )
    )

    @pydantic.model_validator(mode="after")
    def validate_eligibility(self) -> typing.Self:
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

    outcome: DividendRecommendationOutcome = pydantic.Field(
        description="Preferred strategy or the reason no strategy is preferred."
    )
    probability_advantage: float | None = pydantic.Field(
        default=None,
        ge=0,
        le=1,
        allow_inf_nan=False,
        description="Absolute success-probability advantage of the preferred strategy.",
    )
    rationale: models_types.NonEmptyString = pydantic.Field(
        max_length=4000,
        description="Evidence-based explanation of the comparison outcome.",
    )
    reference_ids: list[typing.Annotated[models_types.NonEmptyString, pydantic.Field(max_length=4000)]] = (
        pydantic.Field(
            min_length=1,
            max_length=6,
            description="Identifiers of sources supporting the recommendation.",
        )
    )


class DividendEventAnalysis(models_ai.StrictAIModel):
    """Final structured analysis of a dividend event and two trading strategies.

    Complete and CompleteWithWarnings mean the workflow completed, not that
    every estimate was obtainable. When validated evidence is insufficient,
    these results may retain null evidence-adjusted estimates while keeping both
    strategy assessments and an InsufficientInsights recommendation. They
    require research and references, with warnings absent or present
    respectively. Failed results require a failure reason, contain no strategy
    results or validation warnings, and may retain references only when retained
    research uses them.
    """

    as_of: datetime.datetime = pydantic.Field(description="Timezone-aware timestamp when analysis was finalized.")
    analysis_status: DividendAnalysisStatus = pydantic.Field(
        description="Completion state of the dividend-event analysis."
    )
    failure_reason: str | None = pydantic.Field(
        description="Failure detail when analysis_status is Failed; otherwise null."
    )
    overall_data_quality: models_types.DataQuality = pydantic.Field(
        description="Overall quality of historical and researched evidence."
    )
    event: DividendEventContext = pydantic.Field(description="Verified security and dividend-event context.")
    historical_baseline: DividendHistoricalBaseline = pydantic.Field(
        description="Deterministic historical and technical baseline."
    )
    research: DividendResearch | None = pydantic.Field(
        description="Validated sourced research, or null when research failed."
    )
    evidence_adjusted_ex_date_close_drop: DividendDropEstimate | None = pydantic.Field(
        description=(
            "Research-adjusted ex-date close-drop estimate, or null when validated evidence is insufficient "
            "to produce that estimate; Failed results also use null."
        )
    )
    evidence_adjusted_pre_ex_close_recovery: DividendRecoveryEstimate | None = pydantic.Field(
        description=(
            "Research-adjusted recovery estimate to the pre-ex close, or null when validated evidence is "
            "insufficient to produce that estimate; Failed results also use null."
        )
    )
    evidence_adjusted_capture_break_even_recovery: DividendRecoveryEstimate | None = pydantic.Field(
        description=(
            "Research-adjusted recovery estimate to capture break-even, or null when validated evidence is "
            "insufficient to produce that estimate; Failed results also use null."
        )
    )
    evidence_adjusted_discount_break_even_recovery: DividendRecoveryEstimate | None = pydantic.Field(
        description=(
            "Research-adjusted recovery estimate to discount-entry break-even, or null when validated evidence "
            "is insufficient to produce that estimate; Failed results also use null."
        )
    )
    dividend_capture: DividendStrategyAssessment | None = pydantic.Field(
        description="Dividend-capture strategy assessment, or null on failure."
    )
    post_dividend_discount: DividendStrategyAssessment | None = pydantic.Field(
        description="Post-dividend-discount strategy assessment, or null on failure."
    )
    recommendation: DividendRecommendation | None = pydantic.Field(
        description="Comparison outcome across strategies, or null on failure."
    )
    validation_warnings: list[typing.Annotated[models_types.NonEmptyString, pydantic.Field(max_length=4000)]] = (
        pydantic.Field(
            max_length=20,
            description="Application corrections or validation caveats applied to AI output.",
        )
    )
    references: list[models_ai.ReferenceSource] = pydantic.Field(
        max_length=6,
        description="Canonical sources cited by research and assessment, in application-supplied order.",
    )

    @pydantic.model_validator(mode="after")
    def validate_analysis(self) -> typing.Self:
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
