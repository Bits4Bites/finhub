from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from ..utils import ai_reference as ai_reference_utils
from . import ai as models_ai
from . import portfolio as models_portfolio
from . import types as models_types

PortfolioSpotlightRiskLevel = Literal["Critical", "High", "Medium"]
PortfolioSpotlightActionTiming = Literal[
    "AsSoonAsPossibleWithinOneWeek",
    "WithinOneToTwoWeeks",
    "Monitor",
]
PortfolioSpotlightAnalysisStatus = Literal["Complete", "CompleteWithWarnings"]
PortfolioSpotlightRebalanceFlag = Literal["YES", "NO"]

_ACTION_TIMING_BY_RISK_LEVEL: dict[PortfolioSpotlightRiskLevel, PortfolioSpotlightActionTiming] = {
    "Critical": "AsSoonAsPossibleWithinOneWeek",
    "High": "WithinOneToTwoWeeks",
    "Medium": "Monitor",
}
_RISK_LEVEL_ORDER: dict[PortfolioSpotlightRiskLevel, int] = {
    "Critical": 0,
    "High": 1,
    "Medium": 2,
}


class PortfolioSpotlightSnapshot(models_ai.StrictAIModel):
    """Verified portfolio state used as the basis for spotlight analysis.

    Total market value and holding valuations are service-supplied rather than
    recomputed by this model. Supplied holding allocations must be unique by
    ticker, share one currency, and sum to one.
    """

    as_of: datetime = Field(description="Timezone-aware timestamp of the verified portfolio snapshot.")
    country: models_types.CountryCode = Field(
        description="ISO 3166-1 alpha-2 market country code; input is trimmed and uppercased.",
    )
    currency: models_types.CurrencyCode = Field(
        description=("Three-letter currency shared by every verified holding; input is trimmed and uppercased."),
    )
    total_market_value: float = Field(
        gt=0,
        allow_inf_nan=False,
        description="Service-verified total current market value supplied for the snapshot.",
    )
    holdings: list[models_portfolio.PortfolioVerifiedHolding] = Field(
        min_length=1,
        max_length=50,
        description="Verified positions and their service-supplied current allocations.",
    )
    data_gaps: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(
        max_length=20,
        description="Known limitations in portfolio verification or valuation data.",
    )

    @model_validator(mode="after")
    def validate_snapshot(self) -> Self:
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("snapshot as_of must be timezone-aware")
        tickers = [holding.ticker for holding in self.holdings]
        if len(tickers) != len(set(tickers)):
            raise ValueError("snapshot holding tickers must be unique")
        allocation_total = sum(holding.current_allocation for holding in self.holdings)
        if abs(allocation_total - 1.0) > 1e-6:
            raise ValueError("snapshot current allocations must sum to one")
        if {holding.currency for holding in self.holdings} != {self.currency}:
            raise ValueError("snapshot holdings must use the snapshot currency")
        return self


class PortfolioSpotlightRiskAction(models_ai.StrictAIModel):
    """A ranked portfolio risk with a bounded response action.

    Critical risks use AsSoonAsPossibleWithinOneWeek, High risks use
    WithinOneToTwoWeeks, and Medium risks use Monitor.
    """

    rank: int = Field(ge=1, le=4, description="One-based priority rank among returned risks.")
    level: PortfolioSpotlightRiskLevel = Field(description="Urgency assigned to the portfolio risk.")
    action_timing: PortfolioSpotlightActionTiming = Field(
        description=(
            "Required response window: AsSoonAsPossibleWithinOneWeek for "
            "Critical, WithinOneToTwoWeeks for High, and Monitor for Medium."
        )
    )
    risk: models_types.NonEmptyString = Field(
        max_length=4000,
        description="Concise description of the material portfolio risk.",
    )
    action: models_types.NonEmptyString = Field(
        max_length=4000,
        description="Specific action or monitoring trigger recommended for the risk.",
    )
    affected_tickers: list[
        Annotated[
            models_types.NonEmptyString,
            Field(max_length=models_portfolio.MAX_TICKER_LENGTH),
        ]
    ] = Field(
        min_length=1,
        max_length=50,
        description=(
            "Canonical EXCHANGE:CODE verified-portfolio tickers affected by the "
            "risk; inputs are trimmed, uppercased, and alias-normalized."
        ),
    )
    requires_rebalance: bool = Field(description="Whether the action changes portfolio composition or allocation.")
    confidence: int = Field(
        ge=0,
        le=100,
        description="Confidence score for the risk and action from zero through 100.",
    )
    data_gaps: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(
        max_length=20,
        description="Evidence limitations specific to this risk.",
    )
    reference_ids: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(
        max_length=6,
        description="Identifiers of response references supporting this risk.",
    )

    @field_validator("affected_tickers", mode="after")
    @classmethod
    def normalize_tickers(cls, value: list[str]) -> list[str]:
        return [models_portfolio.normalize_canonical_ticker(ticker) for ticker in value]

    @model_validator(mode="after")
    def validate_action(self) -> Self:
        if self.action_timing != _ACTION_TIMING_BY_RISK_LEVEL[self.level]:
            raise ValueError("action_timing is inconsistent with risk level")
        if len(self.affected_tickers) != len(set(self.affected_tickers)):
            raise ValueError("affected_tickers must be unique")
        if len(self.reference_ids) != len(set(self.reference_ids)):
            raise ValueError("reference_ids must be unique")
        return self


class PortfolioSpotlightAnalysis(models_ai.StrictAIModel):
    """Final structured portfolio spotlight review.

    Complete results have no validation warnings; CompleteWithWarnings results
    have at least one. Empty portfolios contain no snapshot, risks, or
    references, cannot recommend rebalancing, and report Insufficient quality.
    Non-empty risks are ranked consecutively from highest to lowest urgency.
    """

    as_of: datetime = Field(description="Timezone-aware timestamp when the analysis was finalized.")
    analysis_status: PortfolioSpotlightAnalysisStatus = Field(
        description="Completion status, including whether validation warnings were produced."
    )
    portfolio_empty: bool = Field(description="Whether the request contained no positions with positive holdings.")
    overall_data_quality: models_types.DataQuality = Field(
        description="Overall quality of the evidence supporting the analysis."
    )
    snapshot: PortfolioSpotlightSnapshot | None = Field(
        description="Verified portfolio snapshot, or null for an empty portfolio."
    )
    risks: list[PortfolioSpotlightRiskAction] = Field(
        max_length=4,
        description="Highest-priority portfolio risks and actions.",
    )
    rebalance_recommended: PortfolioSpotlightRebalanceFlag = Field(
        description="YES when any returned action requires portfolio rebalancing; otherwise NO."
    )
    data_gaps: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(
        max_length=20,
        description="Known limitations across verification, planning, research, and assessment.",
    )
    validation_warnings: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(
        max_length=20,
        description="Application validation or source-verification warnings.",
    )
    references: list[models_ai.ReferenceSource] = Field(
        max_length=6,
        description="Canonical sources cited by the returned risks, in application-supplied order.",
    )

    @model_validator(mode="after")
    def validate_analysis(self) -> Self:
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("analysis as_of must be timezone-aware")
        if self.analysis_status == "Complete" and self.validation_warnings:
            raise ValueError("Complete analysis cannot have validation warnings")
        if self.analysis_status == "CompleteWithWarnings" and not self.validation_warnings:
            raise ValueError("CompleteWithWarnings analysis requires validation warnings")

        if self.portfolio_empty:
            if self.snapshot is not None or self.risks or self.references:
                raise ValueError("empty portfolio analysis cannot contain a snapshot, risks, or references")
            if self.rebalance_recommended != "NO":
                raise ValueError("empty portfolio cannot recommend rebalancing")
            if self.overall_data_quality != "Insufficient":
                raise ValueError("empty portfolio data quality must be Insufficient")
        else:
            if self.snapshot is None:
                raise ValueError("non-empty portfolio analysis requires a snapshot")
            expected_ranks = list(range(1, len(self.risks) + 1))
            if [risk.rank for risk in self.risks] != expected_ranks:
                raise ValueError("risk ranks must be consecutive and start at one")
            level_order = [_RISK_LEVEL_ORDER[risk.level] for risk in self.risks]
            if level_order != sorted(level_order):
                raise ValueError("risks must be ordered from highest to lowest level")
            known_tickers = {holding.ticker for holding in self.snapshot.holdings}
            unknown_tickers = {
                ticker for risk in self.risks for ticker in risk.affected_tickers if ticker not in known_tickers
            }
            if unknown_tickers:
                raise ValueError(f"risks contain unknown tickers: {sorted(unknown_tickers)}")
            expected_rebalance = "YES" if any(risk.requires_rebalance for risk in self.risks) else "NO"
            if self.rebalance_recommended != expected_rebalance:
                raise ValueError("rebalance flag is inconsistent with risk actions")

        ai_reference_utils.validate_reference_registry(self.references, self)
        return self
