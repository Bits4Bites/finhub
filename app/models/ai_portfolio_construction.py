from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from ..utils import ai_reference as ai_reference_utils
from . import ai as models_ai
from . import portfolio as models_portfolio
from . import types as models_types

PortfolioConstructionMode = Literal["Scratch", "Seeded"]
PortfolioConstructionStatus = Literal["Complete", "CompleteWithWarnings"]


class PortfolioTargetPosition(models_ai.StrictAIModel):
    """A security and allocation in the constructed target portfolio."""

    ticker: str = Field(
        min_length=1,
        max_length=models_portfolio.MAX_TICKER_LENGTH,
        description="Canonical EXCHANGE:CODE symbol for the target security.",
    )
    company_name: str | None = Field(
        default=None,
        max_length=models_portfolio.MAX_COMPANY_NAME_LENGTH,
        description="Issuer or security name when established by research.",
    )
    allocation: float = Field(
        gt=0,
        le=1,
        allow_inf_nan=False,
        description="Target portfolio weight expressed from greater than zero through one.",
    )
    role: models_types.NonEmptyString = Field(
        max_length=1000,
        description="Intended role of the security within the target portfolio.",
    )
    rationale: models_types.NonEmptyString = Field(
        max_length=4000,
        description="Theme-aware rationale for including the security at this weight.",
    )
    reference_ids: list[Annotated[models_types.NonEmptyString, Field(max_length=128)]] = Field(
        min_length=1,
        max_length=6,
        description="Identifiers of response references supporting this position.",
    )

    @field_validator("ticker", mode="before")
    @classmethod
    def normalize_ticker(cls, value: object) -> object:
        return models_portfolio.normalize_canonical_ticker(value)

    @model_validator(mode="after")
    def validate_position(self) -> Self:
        if len(self.reference_ids) != len(set(self.reference_ids)):
            raise ValueError("reference_ids must be unique")
        return self


class PortfolioConstruction(models_ai.StrictAIModel):
    """A research-backed target portfolio expressed as allocation percentages."""

    as_of: datetime = Field(description="Timezone-aware timestamp when the portfolio was finalized.")
    construction_status: PortfolioConstructionStatus = Field(
        description="Completion status, including whether source-validation warnings were produced."
    )
    construction_mode: PortfolioConstructionMode = Field(
        description="Scratch without positive seed holdings, or Seeded when verified holdings informed construction."
    )
    country: str = Field(
        min_length=2,
        max_length=2,
        description="ISO 3166-1 alpha-2 market country code used for construction.",
    )
    investor_theme: models_types.NonEmptyString = Field(
        max_length=4000,
        description="Investor goals, constraints, preferences, and risk context used to construct the portfolio.",
    )
    summary: models_types.NonEmptyString = Field(
        max_length=4000,
        description="Concise explanation of the resulting target portfolio.",
    )
    verified_seed_holdings: list[models_portfolio.PortfolioVerifiedHolding] = Field(
        max_length=50,
        description="Positive starting holdings verified before construction; empty in Scratch mode.",
    )
    target_portfolio: list[PortfolioTargetPosition] = Field(
        min_length=3,
        max_length=20,
        description="Constructed target holdings whose allocation weights sum to one.",
    )
    overall_data_quality: models_types.DataQuality = Field(
        description="Overall quality of the evidence supporting the constructed portfolio."
    )
    data_gaps: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(
        max_length=20,
        description="Known limitations across verification, planning, research, and construction.",
    )
    validation_warnings: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(
        max_length=20,
        description="Application source-verification warnings affecting the result.",
    )
    references: list[models_ai.ReferenceSource] = Field(
        min_length=1,
        max_length=20,
        description="Canonical sources cited by target portfolio positions.",
    )

    @model_validator(mode="after")
    def validate_construction(self) -> Self:
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        if self.construction_status == "Complete" and self.validation_warnings:
            raise ValueError("Complete construction cannot have validation warnings")
        if self.construction_status == "CompleteWithWarnings" and not self.validation_warnings:
            raise ValueError("CompleteWithWarnings construction requires validation warnings")
        if self.construction_mode == "Scratch" and self.verified_seed_holdings:
            raise ValueError("Scratch construction cannot contain verified seed holdings")
        if self.construction_mode == "Seeded" and not self.verified_seed_holdings:
            raise ValueError("Seeded construction requires verified seed holdings")

        tickers = [position.ticker for position in self.target_portfolio]
        if len(tickers) != len(set(tickers)):
            raise ValueError("target portfolio tickers must be unique")
        allocation_total = sum(position.allocation for position in self.target_portfolio)
        if abs(allocation_total - 1.0) > 1e-6:
            raise ValueError("target portfolio allocations must sum to one")

        seed_tickers = [holding.ticker for holding in self.verified_seed_holdings]
        if len(seed_tickers) != len(set(seed_tickers)):
            raise ValueError("verified seed holding tickers must be unique")

        ai_reference_utils.validate_reference_registry(self.references, self)
        return self
