from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import (
    Field,
    SerializationInfo,
    SerializerFunctionWrapHandler,
    field_validator,
    model_serializer,
    model_validator,
)

from ..utils import ai_reference as ai_reference_utils
from . import ai as models_ai
from . import portfolio as models_portfolio
from . import types as models_types

PortfolioConstructionMode = Literal["Scratch", "Seeded"]
PortfolioConstructionStatus = Literal["Complete", "CompleteWithWarnings"]
PortfolioBudgetType = Literal["NotProvided", "Total", "Recurring"]
PortfolioBudgetFrequency = Literal["Weekly", "Fortnightly", "Monthly", "Quarterly", "Annually"]
PortfolioActionType = Literal["EXIT", "TRIM", "BUY", "ACCUMULATE", "HOLD"]


class PortfolioBudget(models_ai.StrictAIModel):
    """Supplied or application-inferred new money available for portfolio actions."""

    budget_type: PortfolioBudgetType = Field(
        description="Whether no budget is available, or new money is a total amount or recurring contribution."
    )
    is_inferred: bool = Field(
        description="Whether the application inferred the recurring next-iteration budget from current holdings."
    )
    amount: float | None = Field(
        gt=0,
        allow_inf_nan=False,
        description="Positive new-money amount for one action-plan iteration, or null when no budget is available.",
    )
    currency: str | None = Field(
        min_length=3,
        max_length=3,
        description="Three-letter budget currency, or null when no budget is available.",
    )
    frequency: PortfolioBudgetFrequency | None = Field(
        description="Investor-supplied contribution frequency, or null for total and inferred next-iteration budgets.",
    )
    source_text: str | None = Field(
        min_length=1,
        max_length=500,
        description="Exact investor-theme excerpt or deterministic explanation of an inferred budget.",
    )

    @field_validator("currency", mode="before")
    @classmethod
    def normalize_currency(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip().upper()
        if not normalized.isascii() or not normalized.isalpha():
            raise ValueError("currency must be a three-letter ISO code")
        return normalized

    @model_validator(mode="after")
    def validate_budget(self) -> Self:
        if self.budget_type == "NotProvided":
            if self.is_inferred or any(
                value is not None for value in (self.amount, self.currency, self.frequency, self.source_text)
            ):
                raise ValueError("NotProvided budget cannot contain budget details")
        elif self.budget_type == "Total":
            if self.amount is None or self.currency is None or self.source_text is None:
                raise ValueError("Total budget requires amount, currency, and source_text")
            if self.is_inferred:
                raise ValueError("Total budget cannot be application-inferred")
            if self.frequency is not None:
                raise ValueError("Total budget cannot contain a recurring frequency")
        elif self.amount is None or self.currency is None or self.source_text is None:
            raise ValueError("Recurring budget requires amount, currency, and source_text")
        elif self.is_inferred and self.frequency is not None:
            raise ValueError("Inferred recurring budget cannot invent a contribution frequency")
        elif not self.is_inferred and self.frequency is None:
            raise ValueError("Investor-supplied recurring budget requires a frequency")
        return self


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


class PortfolioActionStep(models_ai.StrictAIModel):
    """One prioritized whole-share implementation action for the target portfolio."""

    priority: int = Field(
        ge=1,
        le=70,
        description="One-based action priority, with the most important action first.",
    )
    action: PortfolioActionType = Field(description="Required portfolio implementation action.")
    ticker: str = Field(
        min_length=1,
        max_length=models_portfolio.MAX_TICKER_LENGTH,
        description="Canonical EXCHANGE:CODE symbol affected by the action.",
    )
    company_name: str | None = Field(
        default=None,
        max_length=models_portfolio.MAX_COMPANY_NAME_LENGTH,
        description="Issuer or security name when available.",
    )
    instruction: models_types.NonEmptyString = Field(
        max_length=1000,
        description="Concise executable instruction, such as SELL ALL or BUY a whole-share quantity.",
    )
    quantity: int | None = Field(
        default=None,
        ge=1,
        description="Whole-share quantity for BUY or TRIM, otherwise null.",
    )
    market_price: float | None = Field(
        default=None,
        gt=0,
        allow_inf_nan=False,
        description="Verified market price used for sizing or an EXIT estimate, when available.",
    )
    estimated_amount: float | None = Field(
        default=None,
        ge=0,
        allow_inf_nan=False,
        description="Estimated cash required or released by the action, or null when not quantifiable.",
    )
    target_allocation: float | None = Field(
        default=None,
        gt=0,
        le=1,
        allow_inf_nan=False,
        description="Target portfolio weight for actions involving a selected security.",
    )
    reasoning: models_types.NonEmptyString = Field(
        max_length=4000,
        description="Brief explanation of why this action has its assigned priority.",
    )
    reference_ids: list[Annotated[models_types.NonEmptyString, Field(max_length=128)]] = Field(
        max_length=6,
        description="Identifiers of response references supporting the action.",
    )

    @field_validator("ticker", mode="before")
    @classmethod
    def normalize_ticker(cls, value: object) -> object:
        return models_portfolio.normalize_canonical_ticker(value)

    @model_validator(mode="after")
    def validate_step(self) -> Self:
        if len(self.reference_ids) != len(set(self.reference_ids)):
            raise ValueError("action reference_ids must be unique")
        if self.action in {"TRIM", "BUY"}:
            if self.quantity is None:
                raise ValueError("BUY and TRIM actions require a whole-share quantity")
            if self.market_price is None or self.estimated_amount is None:
                raise ValueError("BUY and TRIM actions require market price and estimated amount")
        elif self.quantity is not None:
            raise ValueError("Only BUY and TRIM actions can contain a quantity")
        if self.action == "ACCUMULATE" and self.target_allocation is None:
            raise ValueError("ACCUMULATE actions require a target allocation")
        if self.action == "EXIT" and not self.instruction.upper().startswith("SELL ALL"):
            raise ValueError("EXIT actions must use a SELL ALL instruction")
        return self


class PortfolioActionPlan(models_ai.StrictAIModel):
    """Prioritized implementation steps derived from the constructed target and budget."""

    budget: PortfolioBudget = Field(description="Normalized investment budget used to size the action plan.")
    summary: models_types.NonEmptyString = Field(
        max_length=4000,
        description="Concise implementation summary for the prioritized actions.",
    )
    budget_utilized: float | None = Field(
        default=None,
        ge=0,
        allow_inf_nan=False,
        description="New-money budget spent on whole-share purchases.",
    )
    unallocated_amount: float | None = Field(
        default=None,
        ge=0,
        allow_inf_nan=False,
        description="Budget left unallocated because only whole shares may be traded.",
    )
    steps: list[PortfolioActionStep] = Field(
        min_length=1,
        max_length=70,
        description="Implementation actions ordered from highest to lowest priority.",
    )

    @model_validator(mode="after")
    def validate_action_plan(self) -> Self:
        priorities = [step.priority for step in self.steps]
        if priorities != list(range(1, len(self.steps) + 1)):
            raise ValueError("action priorities must be consecutive and start at one")
        tickers = [step.ticker for step in self.steps]
        if len(tickers) != len(set(tickers)):
            raise ValueError("action plan tickers must be unique")

        if self.budget.budget_type == "NotProvided":
            raise ValueError("action plan requires a supplied or inferred budget")
        if self.budget_utilized is None or self.unallocated_amount is None:
            raise ValueError("budget-aware action plan requires utilized and unallocated amounts")
        if self.budget.amount is None:
            raise ValueError("budget-aware action plan requires a budget amount")
        if abs(self.budget_utilized + self.unallocated_amount - self.budget.amount) > 0.01:
            raise ValueError("utilized and unallocated amounts must equal the action-plan budget")
        if any(step.action == "TRIM" for step in self.steps):
            raise ValueError("new-money action plan cannot contain TRIM actions")
        if self.budget.budget_type == "Recurring":
            buy_total = sum(step.estimated_amount or 0 for step in self.steps if step.action == "BUY")
            if self.budget.amount is not None and buy_total - self.budget.amount > 0.01:
                raise ValueError("recurring BUY actions cannot exceed the contribution budget")
        return self


class PortfolioConstruction(models_ai.StrictAIModel):
    """A research-backed target portfolio with prioritized implementation actions."""

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
    action_plan: PortfolioActionPlan | None = Field(
        description=(
            "Prioritized whole-share implementation plan, or null when neither a budget nor current holdings exist."
        )
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

    @model_serializer(mode="wrap")
    def serialize_action_plan(
        self,
        handler: SerializerFunctionWrapHandler,
        info: SerializationInfo,
    ):
        data = handler(self)
        included = info.include
        excluded = info.exclude
        action_plan_included = included is None or (
            isinstance(included, dict | set | frozenset) and "action_plan" in included
        )
        action_plan_excluded = isinstance(excluded, dict | set | frozenset) and "action_plan" in excluded
        if self.action_plan is None and info.exclude_none and action_plan_included and not action_plan_excluded:
            data["action_plan"] = None
        return data

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

        target_tickers = set(tickers)
        seed_ticker_set = set(seed_tickers)
        if self.action_plan is None:
            if self.construction_mode != "Scratch":
                raise ValueError("Seeded construction requires an action plan")
        else:
            action_tickers = {step.ticker for step in self.action_plan.steps}
            if action_tickers != target_tickers | seed_ticker_set:
                raise ValueError("action plan must cover every target and verified seed ticker")
            target_allocations = {position.ticker: position.allocation for position in self.target_portfolio}
            for step in self.action_plan.steps:
                if step.action in {"BUY", "ACCUMULATE"} and step.ticker not in target_tickers:
                    raise ValueError(f"{step.action} action contains a ticker outside the target portfolio")
                if step.action in {"EXIT", "TRIM"} and step.ticker not in seed_ticker_set:
                    raise ValueError(f"{step.action} action contains a ticker outside verified seed holdings")
                if step.action == "EXIT" and step.ticker in target_tickers:
                    raise ValueError("EXIT action cannot contain a target portfolio ticker")
                if step.action == "TRIM" and step.ticker not in target_tickers:
                    raise ValueError("TRIM action requires a retained target portfolio ticker")
                if step.action == "HOLD" and step.ticker not in target_tickers:
                    raise ValueError("HOLD action contains a ticker outside the target portfolio")
                if step.target_allocation is not None and step.ticker not in target_tickers:
                    raise ValueError("action target allocation requires a target portfolio ticker")
                if step.ticker in target_allocations and (
                    step.target_allocation is None
                    or abs(step.target_allocation - target_allocations[step.ticker]) > 1e-6
                ):
                    raise ValueError("action target allocation must match the target portfolio")
            if self.verified_seed_holdings and self.action_plan.budget.currency is not None:
                seed_currencies = {holding.currency for holding in self.verified_seed_holdings}
                if seed_currencies != {self.action_plan.budget.currency}:
                    raise ValueError("action budget currency must match verified seed holdings")

        ai_reference_utils.validate_reference_registry(self.references, self)
        return self
