from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from ..utils import ai_reference as ai_reference_utils
from . import ai as models_ai
from . import portfolio as models_portfolio
from . import types as models_types

TickerAnalysisStatus = Literal["Complete", "CompleteWithWarnings"]
TickerForecastHorizon = Literal["OneWeek", "TwoWeeks", "OneMonth", "ThreeMonths"]
TickerForecastAssessmentStatus = Literal["Forecast", "InsufficientData"]
TickerPriceDirection = Literal["Up", "Flat", "Down", "Mixed", "InsufficientData"]
TickerRecommendationAction = Literal["BUY", "HOLD", "SELL"]
TickerRecommendationScope = Literal["NewPosition", "ExistingHolding"]

_HORIZON_DAYS: dict[TickerForecastHorizon, int] = {
    "OneWeek": 7,
    "TwoWeeks": 14,
    "OneMonth": 30,
    "ThreeMonths": 90,
}
_FORECAST_HORIZON_ORDER: tuple[TickerForecastHorizon, ...] = (
    "OneWeek",
    "TwoWeeks",
    "OneMonth",
    "ThreeMonths",
)


class TickerPriceRange(models_ai.StrictAIModel):
    """A positive price interval in the security's trading currency."""

    minimum: float = Field(gt=0, allow_inf_nan=False, description="Lower bound of the price range.")
    maximum: float = Field(gt=0, allow_inf_nan=False, description="Upper bound of the price range.")
    currency: str = Field(
        min_length=3,
        max_length=3,
        description="Three-letter trading currency code.",
    )

    @field_validator("currency", mode="before")
    @classmethod
    def normalize_currency(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        if self.minimum > self.maximum:
            raise ValueError("minimum must not exceed maximum")
        return self


class TickerMarketSnapshot(models_ai.StrictAIModel):
    """Verified quote, historical, technical, and consensus inputs for ticker analysis."""

    as_of: datetime = Field(description="Timezone-aware timestamp of the verified market snapshot.")
    symbol: str = Field(
        min_length=1,
        max_length=models_portfolio.MAX_TICKER_LENGTH,
        description="Canonical EXCHANGE:CODE symbol.",
    )
    company_name: str | None = Field(
        default=None,
        max_length=models_portfolio.MAX_COMPANY_NAME_LENGTH,
        description="Issuer or security name, when available.",
    )
    asset_type: models_types.AssetType = Field(description="Normalized asset classification.")
    exchange: str = Field(
        min_length=1,
        max_length=models_portfolio.MAX_EXCHANGE_LENGTH,
        description="Normalized exchange code.",
    )
    country: str = Field(
        min_length=2,
        max_length=2,
        description="ISO 3166-1 alpha-2 market country code.",
    )
    currency: str = Field(
        min_length=3,
        max_length=3,
        description="Three-letter trading currency code.",
    )
    sector: str | None = Field(default=None, max_length=200, description="Provider-reported sector.")
    industry: str | None = Field(default=None, max_length=200, description="Provider-reported industry.")
    market_price: float = Field(gt=0, allow_inf_nan=False, description="Verified current market price.")
    previous_close: float | None = Field(
        default=None,
        gt=0,
        allow_inf_nan=False,
        description="Previous regular-session closing price.",
    )
    market_day_low: float | None = Field(
        default=None,
        gt=0,
        allow_inf_nan=False,
        description="Current regular-session low price.",
    )
    market_day_high: float | None = Field(
        default=None,
        gt=0,
        allow_inf_nan=False,
        description="Current regular-session high price.",
    )
    fifty_two_week_low: float | None = Field(
        default=None,
        gt=0,
        allow_inf_nan=False,
        description="Provider-reported 52-week low price.",
    )
    fifty_two_week_high: float | None = Field(
        default=None,
        gt=0,
        allow_inf_nan=False,
        description="Provider-reported 52-week high price.",
    )
    bid: float | None = Field(
        default=None,
        gt=0,
        allow_inf_nan=False,
        description="Current best bid price, when available.",
    )
    ask: float | None = Field(
        default=None,
        gt=0,
        allow_inf_nan=False,
        description="Current best ask price, when available.",
    )
    bid_ask_spread_pct: float | None = Field(
        default=None,
        ge=0,
        allow_inf_nan=False,
        description="Bid-ask spread as a percentage of the midpoint.",
    )
    market_volume: int | None = Field(
        default=None,
        ge=0,
        description="Current regular-session trading volume.",
    )
    market_cap: int | None = Field(
        default=None,
        ge=0,
        description="Provider-reported market capitalization.",
    )
    beta: float | None = Field(
        default=None,
        allow_inf_nan=False,
        description="Provider-reported beta, when available.",
    )
    analyst_recommendation: str | None = Field(
        default=None,
        max_length=200,
        description="Provider-reported analyst recommendation label.",
    )
    analyst_target_low: float | None = Field(
        default=None,
        gt=0,
        allow_inf_nan=False,
        description="Lowest provider-reported analyst price target.",
    )
    analyst_target_mean: float | None = Field(
        default=None,
        gt=0,
        allow_inf_nan=False,
        description="Mean provider-reported analyst price target.",
    )
    analyst_target_median: float | None = Field(
        default=None,
        gt=0,
        allow_inf_nan=False,
        description="Median provider-reported analyst price target.",
    )
    analyst_target_high: float | None = Field(
        default=None,
        gt=0,
        allow_inf_nan=False,
        description="Highest provider-reported analyst price target.",
    )
    return_5d_pct: float | None = Field(
        default=None,
        allow_inf_nan=False,
        description="Verified trailing five-trading-day return percentage.",
    )
    return_10d_pct: float | None = Field(
        default=None,
        allow_inf_nan=False,
        description="Verified trailing ten-trading-day return percentage.",
    )
    return_21d_pct: float | None = Field(
        default=None,
        allow_inf_nan=False,
        description="Verified trailing 21-trading-day return percentage.",
    )
    return_63d_pct: float | None = Field(
        default=None,
        allow_inf_nan=False,
        description="Verified trailing 63-trading-day return percentage.",
    )
    realized_volatility_20d_pct: float | None = Field(
        default=None,
        ge=0,
        allow_inf_nan=False,
        description="Annualized realized volatility from the latest 20 daily returns.",
    )
    realized_volatility_60d_pct: float | None = Field(
        default=None,
        ge=0,
        allow_inf_nan=False,
        description="Annualized realized volatility from the latest 60 daily returns.",
    )
    rsi14: float | None = Field(
        default=None,
        ge=0,
        le=100,
        allow_inf_nan=False,
        description="Latest 14-period relative strength index.",
    )
    ema_trend_pct: float | None = Field(
        default=None,
        allow_inf_nan=False,
        description="Latest exponential-moving-average trend measure in percent.",
    )
    atr14: float | None = Field(
        default=None,
        ge=0,
        allow_inf_nan=False,
        description="Latest 14-period average true range.",
    )
    benchmark_return_21d_pct: float | None = Field(
        default=None,
        allow_inf_nan=False,
        description="Trailing 21-trading-day return of the selected market benchmark.",
    )
    peer_return_21d_pct: float | None = Field(
        default=None,
        allow_inf_nan=False,
        description="Trailing 21-trading-day return of the selected sector or peer benchmark.",
    )
    history_sample_count: int = Field(ge=0, description="Number of valid daily observations used.")
    data_gaps: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(
        max_length=20,
        description="Unavailable or insufficient verified market data.",
    )

    @field_validator("symbol", "exchange", "country", "currency", mode="before")
    @classmethod
    def normalize_identifiers(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_snapshot(self) -> Self:
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("market snapshot as_of must be timezone-aware")
        for low_name, high_name in (
            ("market_day_low", "market_day_high"),
            ("fifty_two_week_low", "fifty_two_week_high"),
            ("analyst_target_low", "analyst_target_high"),
        ):
            low = getattr(self, low_name)
            high = getattr(self, high_name)
            if low is not None and high is not None and low > high:
                raise ValueError(f"{low_name} must not exceed {high_name}")
        if self.bid is not None and self.ask is not None and self.bid > self.ask:
            raise ValueError("bid must not exceed ask")
        return self


class TickerHoldingSnapshot(models_ai.StrictAIModel):
    """Deterministic valuation of an optional current holding."""

    num_shares: float = Field(
        gt=0,
        allow_inf_nan=False,
        description="Positive number of shares or units held.",
    )
    avg_price: float = Field(
        gt=0,
        allow_inf_nan=False,
        description="Average acquisition price per share or unit.",
    )
    currency: str = Field(
        min_length=3,
        max_length=3,
        description="Three-letter trading currency code.",
    )
    market_price: float = Field(
        gt=0,
        allow_inf_nan=False,
        description="Verified current market price used for valuation.",
    )
    cost_basis: float = Field(
        gt=0,
        allow_inf_nan=False,
        description="Total acquisition cost before fees and taxes.",
    )
    market_value: float = Field(
        gt=0,
        allow_inf_nan=False,
        description="Current holding value at the verified market price.",
    )
    unrealized_profit_loss: float = Field(
        allow_inf_nan=False,
        description="Difference between current market value and cost basis.",
    )
    unrealized_return_pct: float = Field(
        allow_inf_nan=False,
        description="Unrealized profit or loss as a percentage of cost basis.",
    )
    break_even_price: float = Field(
        gt=0,
        allow_inf_nan=False,
        description="Per-unit price equal to the supplied average acquisition price.",
    )

    @field_validator("currency", mode="before")
    @classmethod
    def normalize_currency(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_calculations(self) -> Self:
        expected_cost_basis = self.num_shares * self.avg_price
        expected_market_value = self.num_shares * self.market_price
        expected_profit_loss = expected_market_value - expected_cost_basis
        expected_return = expected_profit_loss / expected_cost_basis * 100
        calculations = (
            ("cost_basis", self.cost_basis, expected_cost_basis),
            ("market_value", self.market_value, expected_market_value),
            ("unrealized_profit_loss", self.unrealized_profit_loss, expected_profit_loss),
            ("unrealized_return_pct", self.unrealized_return_pct, expected_return),
            ("break_even_price", self.break_even_price, self.avg_price),
        )
        for name, actual, expected in calculations:
            tolerance = max(0.01, abs(expected) * 1e-6)
            if abs(actual - expected) > tolerance:
                raise ValueError(f"{name} is inconsistent with holding inputs")
        return self


class TickerEvidenceClaim(models_ai.StrictAIModel):
    """One externally sourced factual claim used in ticker analysis."""

    text: models_types.NonEmptyString = Field(
        max_length=4000,
        description="Externally sourced factual statement.",
    )
    reference_ids: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(
        min_length=1,
        max_length=6,
        description="Canonical IDs of sources supporting the claim.",
    )

    @model_validator(mode="after")
    def validate_references(self) -> Self:
        if len(self.reference_ids) != len(set(self.reference_ids)):
            raise ValueError("claim reference_ids must be unique")
        return self


class TickerResearchSection(models_ai.StrictAIModel):
    """One evidence-linked section of deep ticker research."""

    summary: models_types.NonEmptyString = Field(
        max_length=4000,
        description="Concise synthesis of the section's supported evidence.",
    )
    data_quality: models_types.DataQuality = Field(
        description="Quality assessment for the section's available evidence.",
    )
    claims: list[TickerEvidenceClaim] = Field(
        max_length=4,
        description="Source-linked factual claims supporting the section.",
    )
    data_gaps: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(
        max_length=20,
        description="Material evidence limitations for this section.",
    )
    reference_ids: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(
        max_length=12,
        description="Unique canonical source IDs used by this section's claims.",
    )

    @model_validator(mode="after")
    def validate_references(self) -> Self:
        if len(self.reference_ids) != len(set(self.reference_ids)):
            raise ValueError("section reference_ids must be unique")
        claim_ids = {reference_id for claim in self.claims for reference_id in claim.reference_ids}
        if set(self.reference_ids) != claim_ids:
            raise ValueError("section reference_ids must equal the IDs used by its claims")
        if not self.claims and not self.data_gaps:
            raise ValueError("research section without claims requires an explicit data gap")
        return self


class TickerResearch(models_ai.StrictAIModel):
    """Structured deep research used by ticker forecasts and recommendation."""

    as_of: datetime = Field(description="Timezone-aware timestamp when research was finalized.")
    business_profile: TickerResearchSection = Field(
        description="Business model or fund-objective and composition research.",
    )
    financial_performance: TickerResearchSection = Field(
        description="Recent financial or portfolio-performance research.",
    )
    valuation: TickerResearchSection = Field(
        description="Valuation research relative to suitable history and peers.",
    )
    recent_developments: TickerResearchSection = Field(
        description="Material recent filing, announcement, and news research.",
    )
    catalysts: TickerResearchSection = Field(
        description="Evidence-backed potential positive price catalysts.",
    )
    risks: TickerResearchSection = Field(
        description="Evidence-backed security and market risks.",
    )
    market_consensus: TickerResearchSection = Field(
        description="Available analyst, market, or fund consensus research.",
    )
    asset_specific: TickerResearchSection = Field(
        description="Research specific to the security's asset type and market structure.",
    )
    data_gaps: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(
        max_length=20,
        description="Material limitations affecting the research as a whole.",
    )

    @model_validator(mode="after")
    def validate_timestamp(self) -> Self:
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("research as_of must be timezone-aware")
        return self


class TickerPriceForecast(models_ai.StrictAIModel):
    """Validated price-range forecast for one fixed horizon."""

    horizon: TickerForecastHorizon = Field(
        description="Fixed forecast horizon identifier.",
    )
    horizon_days: int = Field(
        ge=1,
        le=90,
        description="Calendar-day baseline for the forecast horizon.",
    )
    period_end: date = Field(
        description="Application-calculated end date for the forecast horizon.",
    )
    assessment_status: TickerForecastAssessmentStatus = Field(
        description="Whether a range was forecast or evidence was insufficient.",
    )
    direction: TickerPriceDirection = Field(
        description="Application-calculated direction implied by the price range.",
    )
    expected_price_min: float | None = Field(
        default=None,
        gt=0,
        allow_inf_nan=False,
        description="Lower expected price bound, or null when data is insufficient.",
    )
    expected_price_max: float | None = Field(
        default=None,
        gt=0,
        allow_inf_nan=False,
        description="Upper expected price bound, or null when data is insufficient.",
    )
    expected_return_min_pct: float | None = Field(
        default=None,
        allow_inf_nan=False,
        description="Return percentage implied by the lower price bound.",
    )
    expected_return_max_pct: float | None = Field(
        default=None,
        allow_inf_nan=False,
        description="Return percentage implied by the upper price bound.",
    )
    confidence: int = Field(
        ge=0,
        le=100,
        description="Forecast confidence score from zero through 100.",
    )
    rationale: models_types.NonEmptyString = Field(
        max_length=4000,
        description="Evidence-based explanation of the forecast range.",
    )
    key_drivers: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(
        max_length=10,
        description="Factors expected to drive price during the horizon.",
    )
    risk_factors: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(
        max_length=10,
        description="Factors that could invalidate or widen the forecast.",
    )
    assumptions: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(
        max_length=10,
        description="Material assumptions underlying the forecast.",
    )
    data_gaps: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(
        max_length=20,
        description="Evidence or history limitations affecting the forecast.",
    )
    reference_ids: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(
        max_length=12,
        description="Canonical source IDs supporting the forecast rationale.",
    )

    @model_validator(mode="after")
    def validate_forecast(self) -> Self:
        if self.horizon_days != _HORIZON_DAYS[self.horizon]:
            raise ValueError("horizon_days is inconsistent with horizon")
        if len(self.reference_ids) != len(set(self.reference_ids)):
            raise ValueError("forecast reference_ids must be unique")

        range_values = (
            self.expected_price_min,
            self.expected_price_max,
            self.expected_return_min_pct,
            self.expected_return_max_pct,
        )
        if self.assessment_status == "Forecast":
            if any(value is None for value in range_values):
                raise ValueError("Forecast assessment requires price and return ranges")
            if self.direction == "InsufficientData":
                raise ValueError("Forecast assessment cannot use InsufficientData direction")
            if self.expected_price_min > self.expected_price_max:
                raise ValueError("expected_price_min must not exceed expected_price_max")
            if self.expected_return_min_pct > self.expected_return_max_pct:
                raise ValueError("expected_return_min_pct must not exceed expected_return_max_pct")
        else:
            if any(value is not None for value in range_values):
                raise ValueError("InsufficientData assessment cannot contain price or return ranges")
            if self.direction != "InsufficientData":
                raise ValueError("InsufficientData assessment must use InsufficientData direction")
            if not self.data_gaps:
                raise ValueError("InsufficientData assessment requires explicit data gaps")
        return self


class TickerRecommendation(models_ai.StrictAIModel):
    """Generic holding-aware BUY, HOLD, or SELL recommendation."""

    action: TickerRecommendationAction = Field(
        description="Generic BUY, HOLD, or SELL action.",
    )
    scope: TickerRecommendationScope = Field(
        description="Whether the action addresses a new position or supplied holding.",
    )
    confidence: int = Field(
        ge=0,
        le=100,
        description="Recommendation confidence score from zero through 100.",
    )
    summary: models_types.NonEmptyString = Field(
        max_length=4000,
        description="Concise explanation of the recommended action.",
    )
    buy_range: TickerPriceRange | None = Field(
        description="Suggested entry range for BUY, otherwise null.",
    )
    sell_range: TickerPriceRange | None = Field(
        description="Suggested reduction or exit range for SELL, otherwise null.",
    )
    reasoning: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(
        min_length=1,
        max_length=10,
        description="Evidence-based reasons supporting the action.",
    )
    key_conditions: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(
        max_length=10,
        description="Conditions under which the recommendation remains applicable.",
    )
    reassessment_triggers: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(
        max_length=10,
        description="Events that should trigger a fresh analysis.",
    )
    risk_warnings: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(
        max_length=10,
        description="Material risks and limitations attached to the action.",
    )
    reference_ids: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(
        max_length=12,
        description="Canonical source IDs supporting the recommendation.",
    )

    @model_validator(mode="after")
    def validate_action_ranges(self) -> Self:
        if len(self.reference_ids) != len(set(self.reference_ids)):
            raise ValueError("recommendation reference_ids must be unique")
        if self.action == "BUY":
            if self.buy_range is None or self.sell_range is not None:
                raise ValueError("BUY requires only buy_range")
        elif self.action == "SELL":
            if self.sell_range is None or self.buy_range is not None:
                raise ValueError("SELL requires only sell_range")
        elif self.buy_range is not None or self.sell_range is not None:
            raise ValueError("HOLD cannot contain buy_range or sell_range")
        return self


class TickerAnalysis(models_ai.StrictAIModel):
    """Final structured deep research, forecast, and recommendation for one ticker."""

    as_of: datetime = Field(description="Timezone-aware timestamp when analysis was finalized.")
    analysis_status: TickerAnalysisStatus = Field(
        description="Whether validation completed without or with non-fatal warnings.",
    )
    symbol: str = Field(
        min_length=1,
        max_length=models_portfolio.MAX_TICKER_LENGTH,
        description="Canonical EXCHANGE:CODE security symbol.",
    )
    company_name: str | None = Field(
        default=None,
        max_length=models_portfolio.MAX_COMPANY_NAME_LENGTH,
        description="Issuer or security name, when available.",
    )
    asset_type: models_types.AssetType = Field(
        description="Normalized asset classification.",
    )
    exchange: str = Field(
        min_length=1,
        max_length=models_portfolio.MAX_EXCHANGE_LENGTH,
        description="Normalized exchange code.",
    )
    country: str = Field(
        min_length=2,
        max_length=2,
        description="ISO 3166-1 alpha-2 market country code.",
    )
    currency: str = Field(
        min_length=3,
        max_length=3,
        description="Three-letter trading currency code.",
    )
    market_snapshot: TickerMarketSnapshot = Field(
        description="Verified deterministic market and historical baseline.",
    )
    holding_snapshot: TickerHoldingSnapshot | None = Field(
        description="Deterministic valuation of the optional supplied holding.",
    )
    research: TickerResearch = Field(
        description="Finalized source-linked deep research.",
    )
    forecasts: list[TickerPriceForecast] = Field(
        min_length=4,
        max_length=4,
        description="One-week, two-week, one-month, and three-month forecasts in order.",
    )
    recommendation: TickerRecommendation = Field(
        description="Final action synthesized from validated research and forecasts.",
    )
    overall_data_quality: models_types.DataQuality = Field(
        description="Aggregate quality of the research and forecasts.",
    )
    data_gaps: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(
        max_length=20,
        description="Material data limitations affecting the final analysis.",
    )
    validation_warnings: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(
        max_length=20,
        description="Non-fatal validation or source-verification warnings.",
    )
    references: list[models_ai.ReferenceSource] = Field(
        min_length=1,
        max_length=12,
        description="Canonical registry of sources cited by the analysis.",
    )

    @field_validator("symbol", "exchange", "country", "currency", mode="before")
    @classmethod
    def normalize_identifiers(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_analysis(self) -> Self:
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("analysis as_of must be timezone-aware")
        if self.analysis_status == "Complete" and self.validation_warnings:
            raise ValueError("Complete analysis cannot have validation warnings")
        if self.analysis_status == "CompleteWithWarnings" and not self.validation_warnings:
            raise ValueError("CompleteWithWarnings requires validation warnings")
        if self.symbol != self.market_snapshot.symbol:
            raise ValueError("analysis symbol must match market snapshot")
        if self.currency != self.market_snapshot.currency:
            raise ValueError("analysis currency must match market snapshot")
        if [forecast.horizon for forecast in self.forecasts] != list(_FORECAST_HORIZON_ORDER):
            raise ValueError("forecasts must contain the four required horizons in order")
        expected_scope: TickerRecommendationScope = (
            "ExistingHolding" if self.holding_snapshot is not None else "NewPosition"
        )
        if self.recommendation.scope != expected_scope:
            raise ValueError("recommendation scope is inconsistent with holding snapshot")
        for price_range in (self.recommendation.buy_range, self.recommendation.sell_range):
            if price_range is not None and price_range.currency != self.currency:
                raise ValueError("recommendation range currency must match analysis currency")
        if self.overall_data_quality == "Insufficient" and self.recommendation.action != "HOLD":
            raise ValueError("Insufficient analysis can only recommend HOLD")
        ai_reference_utils.validate_reference_registry(self.references, self)
        return self
