from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

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
    as_of: datetime
    country: str = Field(min_length=2, max_length=2)
    currency: str = Field(min_length=3, max_length=3)
    total_market_value: float = Field(gt=0, allow_inf_nan=False)
    holdings: list[models_portfolio.PortfolioVerifiedHolding] = Field(min_length=1, max_length=50)
    data_gaps: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(max_length=20)

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
        return self


class PortfolioSpotlightRiskAction(models_ai.StrictAIModel):
    rank: int = Field(ge=1, le=4)
    level: PortfolioSpotlightRiskLevel
    action_timing: PortfolioSpotlightActionTiming
    risk: models_types.NonEmptyString = Field(max_length=4000)
    action: models_types.NonEmptyString = Field(max_length=4000)
    affected_tickers: list[
        Annotated[
            models_types.NonEmptyString,
            Field(max_length=models_portfolio.MAX_TICKER_LENGTH),
        ]
    ] = Field(
        min_length=1,
        max_length=50,
    )
    requires_rebalance: bool
    confidence: int = Field(ge=0, le=100)
    data_gaps: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(max_length=20)
    reference_ids: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(max_length=6)

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
    as_of: datetime
    analysis_status: PortfolioSpotlightAnalysisStatus
    portfolio_empty: bool
    overall_data_quality: models_types.DataQuality
    snapshot: PortfolioSpotlightSnapshot | None
    risks: list[PortfolioSpotlightRiskAction] = Field(max_length=4)
    rebalance_recommended: PortfolioSpotlightRebalanceFlag
    data_gaps: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(max_length=20)
    validation_warnings: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(max_length=20)
    references: list[models_ai.ReferenceSource] = Field(max_length=6)

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
