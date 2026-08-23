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
from . import ai_portfolio_construction as models_construction
from . import portfolio as models_portfolio
from . import types as models_types

PortfolioReviewStatus = Literal["Complete", "CompleteWithWarnings"]
PortfolioReviewStrategy = Literal["LongTerm", "Swing"]
PortfolioReviewRebalanceFlag = Literal["YES", "NO"]
PortfolioReviewRiskLevel = Literal["Critical", "High", "Medium", "Low"]
PortfolioReviewHoldingRecommendation = Literal["HOLD", "TRIM", "EXIT", "BUY_MORE"]
PortfolioReviewExitReason = Literal[
    "CriticalRisk",
    "StructuralChange",
    "SwingRiskControl",
    "SwingThesisInvalidated",
]
PortfolioReviewActionType = Literal[
    "HOLD",
    "TRIM",
    "EXIT",
    "BUY_MORE",
    "INTRODUCE",
    "ACCUMULATE",
]
PortfolioReviewPlanType = Literal["Growth", "Rebalance"]

ROLE_PREFIXES = ("🚀", "🛡️", "🧭", "🧱", "⚡", "💵")
MAJOR_REBALANCE_TURNOVER = 0.20
_ALLOCATION_TOLERANCE = 1e-6
_MONEY_TOLERANCE = 0.01


def _validate_unique_reference_ids(reference_ids: list[str], *, field_name: str) -> None:
    if len(reference_ids) != len(set(reference_ids)):
        raise ValueError(f"{field_name} must be unique")


def _normalize_ticker_list(tickers: list[str]) -> list[str]:
    normalized = [models_portfolio.normalize_canonical_ticker(ticker) for ticker in tickers]
    if len(normalized) != len(set(normalized)):
        raise ValueError("affected_tickers must be unique")
    return normalized


class PortfolioReviewSnapshot(models_ai.StrictAIModel):
    """Verified current portfolio state used by the review."""

    as_of: datetime = Field(description="Timezone-aware timestamp of the verified portfolio snapshot.")
    country: str = Field(
        min_length=2,
        max_length=2,
        description="ISO 3166-1 alpha-2 market country code.",
    )
    currency: str = Field(
        min_length=3,
        max_length=3,
        description="Three-letter currency shared by every verified holding.",
    )
    total_market_value: float = Field(
        gt=0,
        allow_inf_nan=False,
        description="Total current market value of all verified holdings.",
    )
    holdings: list[models_portfolio.PortfolioVerifiedHolding] = Field(
        min_length=1,
        max_length=50,
        description="Positive verified positions and their calculated current allocations.",
    )
    data_gaps: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(
        max_length=20,
        description="Known limitations in portfolio verification or valuation data.",
    )

    @field_validator("country", "currency", mode="before")
    @classmethod
    def normalize_code(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_snapshot(self) -> Self:
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("snapshot as_of must be timezone-aware")
        tickers = [holding.ticker for holding in self.holdings]
        if len(tickers) != len(set(tickers)):
            raise ValueError("snapshot holding tickers must be unique")
        allocation_total = sum(holding.current_allocation for holding in self.holdings)
        if abs(allocation_total - 1.0) > _ALLOCATION_TOLERANCE:
            raise ValueError("snapshot current allocations must sum to one")
        if {holding.currency for holding in self.holdings} != {self.currency}:
            raise ValueError("snapshot holdings must use the snapshot currency")
        return self


class PortfolioReviewStrength(models_ai.StrictAIModel):
    """A research-supported portfolio strength."""

    title: models_types.NonEmptyString = Field(
        max_length=200,
        description="Concise name of the portfolio strength.",
    )
    analysis: models_types.NonEmptyString = Field(
        max_length=4000,
        description="In-depth explanation of why the strength matters to this portfolio.",
    )
    affected_tickers: list[str] = Field(
        min_length=1,
        max_length=50,
        description="Current portfolio tickers contributing to the strength.",
    )
    confidence: int = Field(
        ge=0,
        le=100,
        description="Evidence confidence from zero through 100.",
    )
    data_gaps: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(
        max_length=10,
        description="Evidence limitations specific to this strength.",
    )
    reference_ids: list[Annotated[models_types.NonEmptyString, Field(max_length=128)]] = Field(
        min_length=1,
        max_length=6,
        description="Identifiers of response references supporting the strength.",
    )

    @field_validator("affected_tickers", mode="after")
    @classmethod
    def validate_tickers(cls, value: list[str]) -> list[str]:
        return _normalize_ticker_list(value)

    @model_validator(mode="after")
    def validate_strength(self) -> Self:
        _validate_unique_reference_ids(self.reference_ids, field_name="strength reference_ids")
        return self


class PortfolioReviewRisk(models_ai.StrictAIModel):
    """A material portfolio risk and its practical mitigation."""

    level: PortfolioReviewRiskLevel = Field(description="Materiality of the portfolio risk.")
    risk: models_types.NonEmptyString = Field(
        max_length=4000,
        description="In-depth description of the portfolio risk.",
    )
    impact: models_types.NonEmptyString = Field(
        max_length=4000,
        description="How the risk could affect the portfolio and its stated objective.",
    )
    mitigation: models_types.NonEmptyString = Field(
        max_length=4000,
        description="Practical mitigation or monitoring response.",
    )
    affected_tickers: list[str] = Field(
        min_length=1,
        max_length=50,
        description="Current portfolio tickers exposed to the risk.",
    )
    confidence: int = Field(
        ge=0,
        le=100,
        description="Evidence confidence from zero through 100.",
    )
    data_gaps: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(
        max_length=10,
        description="Evidence limitations specific to this risk.",
    )
    reference_ids: list[Annotated[models_types.NonEmptyString, Field(max_length=128)]] = Field(
        min_length=1,
        max_length=6,
        description="Identifiers of response references supporting the risk.",
    )

    @field_validator("affected_tickers", mode="after")
    @classmethod
    def validate_tickers(cls, value: list[str]) -> list[str]:
        return _normalize_ticker_list(value)

    @model_validator(mode="after")
    def validate_risk(self) -> Self:
        _validate_unique_reference_ids(self.reference_ids, field_name="risk reference_ids")
        return self


class PortfolioHoldingReview(models_ai.StrictAIModel):
    """In-depth assessment of one current holding."""

    ticker: str = Field(
        min_length=1,
        max_length=models_portfolio.MAX_TICKER_LENGTH,
        description="Canonical EXCHANGE:CODE symbol of the current holding.",
    )
    company_name: str | None = Field(
        default=None,
        max_length=models_portfolio.MAX_COMPANY_NAME_LENGTH,
        description="Issuer or security name when available.",
    )
    role: models_types.NonEmptyString = Field(
        max_length=1000,
        description="Application-rendered portfolio role beginning with a standard role emoji.",
    )
    current_allocation: float = Field(
        gt=0,
        le=1,
        allow_inf_nan=False,
        description="Verified current portfolio weight.",
    )
    target_allocation: float = Field(
        ge=0,
        le=1,
        allow_inf_nan=False,
        description="Validated target weight, or zero for an EXIT.",
    )
    thesis: models_types.NonEmptyString = Field(
        max_length=4000,
        description="Current evidence-based investment thesis for the holding.",
    )
    strengths: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(
        min_length=1,
        max_length=8,
        description="Holding-specific strengths relevant to the portfolio objective.",
    )
    risks: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(
        min_length=1,
        max_length=8,
        description="Holding-specific risks relevant to the portfolio objective.",
    )
    recommendation: PortfolioReviewHoldingRecommendation = Field(
        description="Recommended disposition intent for the current holding."
    )
    exit_reason: PortfolioReviewExitReason | None = Field(
        default=None,
        description="Validated LongTerm EXIT basis, or null when the holding is retained.",
    )
    confidence: int = Field(
        ge=0,
        le=100,
        description="Evidence confidence from zero through 100.",
    )
    data_gaps: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(
        max_length=10,
        description="Evidence limitations specific to this holding.",
    )
    reference_ids: list[Annotated[models_types.NonEmptyString, Field(max_length=128)]] = Field(
        min_length=1,
        max_length=6,
        description="Identifiers of response references supporting the holding review.",
    )

    @field_validator("ticker", mode="before")
    @classmethod
    def normalize_ticker(cls, value: object) -> object:
        return models_portfolio.normalize_canonical_ticker(value)

    @model_validator(mode="after")
    def validate_holding_review(self) -> Self:
        if not self.role.startswith(ROLE_PREFIXES):
            raise ValueError("holding role must begin with an application-owned role emoji")
        if self.recommendation == "EXIT":
            if self.target_allocation != 0:
                raise ValueError("EXIT holding review must have zero target allocation")
            if self.exit_reason is None:
                raise ValueError("EXIT holding review requires an exit reason")
        elif self.exit_reason is not None:
            raise ValueError("Only EXIT holding reviews can contain an exit reason")
        _validate_unique_reference_ids(self.reference_ids, field_name="holding review reference_ids")
        return self


class PortfolioReviewTargetPosition(models_ai.StrictAIModel):
    """A retained or introduced security in the validated target portfolio."""

    ticker: str = Field(
        min_length=1,
        max_length=models_portfolio.MAX_TICKER_LENGTH,
        description="Canonical EXCHANGE:CODE symbol for the target security.",
    )
    company_name: str | None = Field(
        default=None,
        max_length=models_portfolio.MAX_COMPANY_NAME_LENGTH,
        description="Issuer or security name when available.",
    )
    current_allocation: float = Field(
        ge=0,
        le=1,
        allow_inf_nan=False,
        description="Current portfolio weight, or zero for an introduced security.",
    )
    target_allocation: float = Field(
        gt=0,
        le=1,
        allow_inf_nan=False,
        description="Validated target portfolio weight.",
    )
    role: models_types.NonEmptyString = Field(
        max_length=1000,
        description="Application-rendered portfolio role beginning with a standard role emoji.",
    )
    rationale: models_types.NonEmptyString = Field(
        max_length=4000,
        description="Evidence-based reason for retaining or introducing the target security.",
    )
    reference_ids: list[Annotated[models_types.NonEmptyString, Field(max_length=128)]] = Field(
        min_length=1,
        max_length=6,
        description="Identifiers of response references supporting the target position.",
    )

    @field_validator("ticker", mode="before")
    @classmethod
    def normalize_ticker(cls, value: object) -> object:
        return models_portfolio.normalize_canonical_ticker(value)

    @model_validator(mode="after")
    def validate_target_position(self) -> Self:
        if not self.role.startswith(ROLE_PREFIXES):
            raise ValueError("target role must begin with an application-owned role emoji")
        _validate_unique_reference_ids(self.reference_ids, field_name="target position reference_ids")
        return self


class PortfolioReviewAction(models_ai.StrictAIModel):
    """One application-calculated portfolio action with AI-authored reasoning."""

    priority: int = Field(
        ge=1,
        le=70,
        description="One-based action priority, with the most important action first.",
    )
    action: PortfolioReviewActionType = Field(description="Required portfolio action.")
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
    current_allocation: float = Field(
        ge=0,
        le=1,
        allow_inf_nan=False,
        description="Verified current weight, or zero for an introduced security.",
    )
    target_allocation: float = Field(
        ge=0,
        le=1,
        allow_inf_nan=False,
        description="Validated target weight, or zero for an EXIT.",
    )
    quantity: int | None = Field(
        default=None,
        ge=1,
        description="Whole-share trade quantity for an executable transaction.",
    )
    market_price: float | None = Field(
        default=None,
        gt=0,
        allow_inf_nan=False,
        description="Verified market price used for sizing, when applicable.",
    )
    estimated_amount: float | None = Field(
        default=None,
        gt=0,
        allow_inf_nan=False,
        description="Estimated cash spent or released by an executable transaction.",
    )
    instruction: models_types.NonEmptyString = Field(
        max_length=1000,
        description="Concise executable instruction for this iteration.",
    )
    reasoning: models_types.NonEmptyString = Field(
        max_length=4000,
        description="Explanation of why this action has its assigned priority.",
    )
    reference_ids: list[Annotated[models_types.NonEmptyString, Field(max_length=128)]] = Field(
        min_length=1,
        max_length=6,
        description="Identifiers of response references supporting the action.",
    )

    @field_validator("ticker", mode="before")
    @classmethod
    def normalize_ticker(cls, value: object) -> object:
        return models_portfolio.normalize_canonical_ticker(value)

    @model_validator(mode="after")
    def validate_action(self) -> Self:
        executable_actions = {"TRIM", "EXIT", "BUY_MORE", "INTRODUCE"}
        if self.action in executable_actions:
            if self.quantity is None or self.market_price is None or self.estimated_amount is None:
                raise ValueError(f"{self.action} requires quantity, market price, and estimated amount")
        elif self.quantity is not None or self.estimated_amount is not None:
            raise ValueError("HOLD and ACCUMULATE cannot contain a quantity or estimated amount")

        if self.action == "EXIT":
            if self.target_allocation != 0:
                raise ValueError("EXIT action must have zero target allocation")
            if not self.instruction.upper().startswith("SELL ALL"):
                raise ValueError("EXIT action must use a SELL ALL instruction")
        elif self.target_allocation <= 0:
            raise ValueError(f"{self.action} requires a positive target allocation")
        if self.action == "ACCUMULATE" and self.market_price is None:
            raise ValueError("ACCUMULATE requires the verified unaffordable market price")
        _validate_unique_reference_ids(self.reference_ids, field_name="action reference_ids")
        return self


class PortfolioReviewCashLedger(models_ai.StrictAIModel):
    """Balanced cash sources and uses for one action-plan iteration."""

    new_money_budget: float = Field(
        gt=0,
        allow_inf_nan=False,
        description="Supplied or inferred new money available for this iteration.",
    )
    estimated_sale_proceeds: float = Field(
        ge=0,
        allow_inf_nan=False,
        description="Estimated cash released by EXIT and TRIM actions.",
    )
    purchase_spend: float = Field(
        ge=0,
        allow_inf_nan=False,
        description="Estimated cash consumed by BUY_MORE and INTRODUCE actions.",
    )
    unallocated_cash: float = Field(
        ge=0,
        allow_inf_nan=False,
        description="Cash remaining after all calculated whole-share transactions.",
    )

    @model_validator(mode="after")
    def validate_ledger(self) -> Self:
        available_cash = self.new_money_budget + self.estimated_sale_proceeds
        used_cash = self.purchase_spend + self.unallocated_cash
        if abs(available_cash - used_cash) > _MONEY_TOLERANCE:
            raise ValueError("cash ledger sources and uses must balance")
        return self


class PortfolioReviewActionPlan(models_ai.StrictAIModel):
    """Prioritized Growth or Rebalance actions for one funded iteration."""

    plan_type: PortfolioReviewPlanType = Field(description="Whether actions implement growth or a major rebalance.")
    budget: models_construction.PortfolioBudget = Field(
        description="Normalized new-money budget used for this action-plan iteration."
    )
    cash_ledger: PortfolioReviewCashLedger = Field(
        description="Balanced new-money, sale-proceeds, purchase, and remaining-cash ledger."
    )
    summary: models_types.NonEmptyString = Field(
        max_length=4000,
        description="Concise execution sequence and budget treatment.",
    )
    actions: list[PortfolioReviewAction] = Field(
        min_length=1,
        max_length=70,
        description="Application-calculated actions ordered from highest to lowest priority.",
    )

    @model_validator(mode="after")
    def validate_action_plan(self) -> Self:
        if self.budget.budget_type == "NotProvided" or self.budget.amount is None:
            raise ValueError("portfolio review action plan requires a supplied or inferred budget")
        if abs(self.cash_ledger.new_money_budget - self.budget.amount) > _MONEY_TOLERANCE:
            raise ValueError("cash ledger new-money budget must match the normalized budget")

        priorities = [action.priority for action in self.actions]
        if priorities != list(range(1, len(self.actions) + 1)):
            raise ValueError("action priorities must be consecutive and start at one")
        action_tickers = [action.ticker for action in self.actions]
        if len(action_tickers) != len(set(action_tickers)):
            raise ValueError("action plan tickers must be unique")

        estimated_sales = sum(
            action.estimated_amount or 0 for action in self.actions if action.action in {"EXIT", "TRIM"}
        )
        estimated_purchases = sum(
            action.estimated_amount or 0 for action in self.actions if action.action in {"BUY_MORE", "INTRODUCE"}
        )
        if abs(estimated_sales - self.cash_ledger.estimated_sale_proceeds) > _MONEY_TOLERANCE:
            raise ValueError("cash ledger sale proceeds must match calculated sale actions")
        if abs(estimated_purchases - self.cash_ledger.purchase_spend) > _MONEY_TOLERANCE:
            raise ValueError("cash ledger purchase spend must match calculated purchase actions")
        return self


class PortfolioReview(models_ai.StrictAIModel):
    """Structured, research-backed review of a verified existing portfolio."""

    result_type: Literal["PortfolioReview"] = Field(
        default="PortfolioReview",
        description="Discriminator identifying an existing-portfolio review result.",
    )
    as_of: datetime = Field(description="Timezone-aware timestamp when the review was finalized.")
    review_status: PortfolioReviewStatus = Field(
        description="Completion status, including whether validation warnings were produced."
    )
    strategy: PortfolioReviewStrategy = Field(description="Deterministically extracted portfolio strategy.")
    country: str = Field(
        min_length=2,
        max_length=2,
        description="ISO 3166-1 alpha-2 market country code used for the review.",
    )
    investor_theme: models_types.NonEmptyString = Field(
        max_length=4000,
        description="Investor goals, constraints, horizon, and risk context used by the review.",
    )
    snapshot: PortfolioReviewSnapshot = Field(description="Verified current portfolio state.")
    budget: models_construction.PortfolioBudget = Field(
        description="Supplied or inferred new-money budget for one action-plan iteration."
    )
    summary: models_types.NonEmptyString = Field(
        max_length=4000,
        description="Concise overall assessment of portfolio alignment, strengths, and risks.",
    )
    strengths: list[PortfolioReviewStrength] = Field(
        min_length=1,
        max_length=10,
        description="Research-supported portfolio strengths.",
    )
    risks: list[PortfolioReviewRisk] = Field(
        min_length=1,
        max_length=10,
        description="Material portfolio risks ordered from highest to lowest severity.",
    )
    holding_reviews: list[PortfolioHoldingReview] = Field(
        min_length=1,
        max_length=50,
        description="One in-depth review for every verified current holding.",
    )
    target_portfolio: list[PortfolioReviewTargetPosition] = Field(
        min_length=1,
        max_length=55,
        description="Validated aspirational target holdings whose weights sum to one.",
    )
    target_turnover: float = Field(
        ge=0,
        le=1,
        allow_inf_nan=False,
        description="One-way turnover between verified current and validated target allocations.",
    )
    rebalance_requested: bool = Field(
        description="Whether the client requested executable actions for a recommended major rebalance."
    )
    rebalance_recommended: PortfolioReviewRebalanceFlag = Field(
        description="YES when EXIT, introduction, or at least 20 percent target turnover requires major rebalancing."
    )
    major_rebalance_reasons: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(
        max_length=10,
        description="Application-derived reasons for recommending a major rebalance.",
    )
    action_plan: PortfolioReviewActionPlan | None = Field(
        description="Structured action plan, or null when an unrequested major rebalance is recommended."
    )
    overall_data_quality: models_types.DataQuality = Field(
        description="Overall quality of the evidence supporting the review."
    )
    data_gaps: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(
        max_length=20,
        description="Known limitations across verification, planning, research, assessment, and target design.",
    )
    validation_warnings: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(
        max_length=20,
        description="Application source-verification or repair warnings affecting the result.",
    )
    references: list[models_ai.ReferenceSource] = Field(
        min_length=1,
        max_length=100,
        description="Canonical sources cited by the structured review.",
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

    @field_validator("country", mode="before")
    @classmethod
    def normalize_country(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_review(self) -> Self:
        self._validate_metadata()
        current = {holding.ticker: holding for holding in self.snapshot.holdings}
        reviews = {review.ticker: review for review in self.holding_reviews}
        targets = {position.ticker: position for position in self.target_portfolio}

        if len(reviews) != len(self.holding_reviews) or set(reviews) != set(current):
            raise ValueError("holding_reviews must contain every verified current holding exactly once")
        if len(targets) != len(self.target_portfolio):
            raise ValueError("target portfolio tickers must be unique")
        if abs(sum(position.target_allocation for position in targets.values()) - 1.0) > _ALLOCATION_TOLERANCE:
            raise ValueError("target portfolio allocations must sum to one")

        self._validate_holding_and_target_coverage(current, reviews, targets)
        calculated_turnover = 0.5 * sum(
            abs(
                (targets[ticker].target_allocation if ticker in targets else 0.0)
                - (current[ticker].current_allocation if ticker in current else 0.0)
            )
            for ticker in set(current) | set(targets)
        )
        if abs(self.target_turnover - calculated_turnover) > _ALLOCATION_TOLERANCE:
            raise ValueError("target_turnover must match current and target allocations")

        introduced_tickers = set(targets) - set(current)
        exited_tickers = set(current) - set(targets)
        expected_recommendation = (
            "YES"
            if introduced_tickers
            or exited_tickers
            or calculated_turnover + _ALLOCATION_TOLERANCE >= MAJOR_REBALANCE_TURNOVER
            else "NO"
        )
        if self.rebalance_recommended != expected_recommendation:
            raise ValueError("rebalance_recommended is inconsistent with target intent and turnover")
        if (expected_recommendation == "YES") != bool(self.major_rebalance_reasons):
            raise ValueError("major_rebalance_reasons must be present exactly when rebalancing is recommended")

        self._validate_action_plan(current, targets)
        self._validate_claim_tickers(current)
        ai_reference_utils.validate_reference_registry(self.references, self)
        return self

    def _validate_metadata(self) -> None:
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("review as_of must be timezone-aware")
        if self.country != self.snapshot.country:
            raise ValueError("review country must match snapshot country")
        if self.review_status == "Complete" and self.validation_warnings:
            raise ValueError("Complete review cannot have validation warnings")
        if self.review_status == "CompleteWithWarnings" and not self.validation_warnings:
            raise ValueError("CompleteWithWarnings review requires validation warnings")
        if self.budget.budget_type == "NotProvided" or self.budget.amount is None:
            raise ValueError("existing-portfolio review requires a supplied or inferred budget")
        if self.budget.currency != self.snapshot.currency:
            raise ValueError("review budget currency must match snapshot currency")

    def _validate_holding_and_target_coverage(
        self,
        current: dict[str, models_portfolio.PortfolioVerifiedHolding],
        reviews: dict[str, PortfolioHoldingReview],
        targets: dict[str, PortfolioReviewTargetPosition],
    ) -> None:
        for ticker, holding in current.items():
            review = reviews[ticker]
            if abs(review.current_allocation - holding.current_allocation) > _ALLOCATION_TOLERANCE:
                raise ValueError("holding review current allocation must match the verified snapshot")
            target = targets.get(ticker)
            if review.recommendation == "EXIT":
                if target is not None:
                    raise ValueError("EXIT holding cannot remain in the target portfolio")
            elif target is None:
                raise ValueError("every retained current holding must appear in the target portfolio")
            elif abs(review.target_allocation - target.target_allocation) > _ALLOCATION_TOLERANCE:
                raise ValueError("holding review target allocation must match the target portfolio")

        for ticker, target in targets.items():
            expected_current_allocation = current[ticker].current_allocation if ticker in current else 0.0
            if abs(target.current_allocation - expected_current_allocation) > _ALLOCATION_TOLERANCE:
                raise ValueError("target current allocation must match the verified snapshot")

        if self.strategy == "LongTerm":
            if any(review.recommendation == "TRIM" for review in reviews.values()):
                raise ValueError("LongTerm holding reviews cannot recommend TRIM")
            if any(
                review.recommendation == "EXIT" and review.exit_reason not in {"CriticalRisk", "StructuralChange"}
                for review in reviews.values()
            ):
                raise ValueError("LongTerm EXIT requires a critical-risk or structural-change reason")

    def _validate_action_plan(
        self,
        current: dict[str, models_portfolio.PortfolioVerifiedHolding],
        targets: dict[str, PortfolioReviewTargetPosition],
    ) -> None:
        if self.rebalance_recommended == "YES" and not self.rebalance_requested:
            if self.action_plan is not None:
                raise ValueError("unrequested recommended rebalance must have a null action plan")
            return
        if self.action_plan is None:
            raise ValueError("portfolio review requires an action plan for this request and recommendation")

        expected_plan_type = "Rebalance" if self.rebalance_recommended == "YES" else "Growth"
        if self.action_plan.plan_type != expected_plan_type:
            raise ValueError("action plan type is inconsistent with the rebalance recommendation")
        if self.action_plan.budget != self.budget:
            raise ValueError("action plan budget must match the review budget")

        actions = {action.ticker: action for action in self.action_plan.actions}
        expected_tickers = set(current) | set(targets)
        if set(actions) != expected_tickers:
            raise ValueError("action plan must cover every current and target ticker")
        if self.strategy == "LongTerm" and any(action.action == "TRIM" for action in actions.values()):
            raise ValueError("LongTerm action plans cannot contain TRIM")

        for ticker, action in actions.items():
            is_current = ticker in current
            is_target = ticker in targets
            if action.action == "EXIT":
                if not is_current or is_target:
                    raise ValueError("EXIT applies only to a current holding omitted from the target")
                if action.quantity != int(current[ticker].num_shares):
                    raise ValueError("EXIT quantity must equal the full current holding")
            elif action.action == "TRIM":
                if not is_current or not is_target:
                    raise ValueError("TRIM applies only to a retained current holding")
                if action.quantity is not None and action.quantity >= int(current[ticker].num_shares):
                    raise ValueError("TRIM quantity must be smaller than the full current holding")
            elif action.action == "BUY_MORE":
                if not is_current or not is_target:
                    raise ValueError("BUY_MORE applies only to an existing target holding")
            elif action.action == "INTRODUCE":
                if is_current or not is_target:
                    raise ValueError("INTRODUCE applies only to a new target holding")
            elif action.action in {"HOLD", "ACCUMULATE"} and not is_target:
                raise ValueError(f"{action.action} applies only to a target holding")

            expected_current = current[ticker].current_allocation if is_current else 0.0
            expected_target = targets[ticker].target_allocation if is_target else 0.0
            if (
                abs(action.current_allocation - expected_current) > _ALLOCATION_TOLERANCE
                or abs(action.target_allocation - expected_target) > _ALLOCATION_TOLERANCE
            ):
                raise ValueError("action allocations must match the current and target portfolios")
            if is_current and action.market_price is not None:
                if abs(action.market_price - current[ticker].market_price) > _MONEY_TOLERANCE:
                    raise ValueError("current-holding action price must match the verified snapshot")
            if (
                action.quantity is not None
                and action.market_price is not None
                and action.estimated_amount is not None
                and abs(action.quantity * action.market_price - action.estimated_amount) > _MONEY_TOLERANCE
            ):
                raise ValueError("action estimated amount must equal quantity multiplied by market price")

    def _validate_claim_tickers(
        self,
        current: dict[str, models_portfolio.PortfolioVerifiedHolding],
    ) -> None:
        known_tickers = set(current)
        for strength in self.strengths:
            unknown = set(strength.affected_tickers) - known_tickers
            if unknown:
                raise ValueError(f"strength contains unknown current tickers: {sorted(unknown)}")
        for risk in self.risks:
            unknown = set(risk.affected_tickers) - known_tickers
            if unknown:
                raise ValueError(f"risk contains unknown current tickers: {sorted(unknown)}")
