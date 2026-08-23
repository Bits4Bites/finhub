from __future__ import annotations

import json
import logging
import re
from datetime import UTC, date, datetime
from decimal import ROUND_FLOOR, Decimal
from typing import Annotated, Literal, Self

import openai
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from .. import config
from ..models import ai as models_ai
from ..models import ai_portfolio_construction as models_construction
from ..models import ai_portfolio_review as models_review
from ..models import portfolio as models_portfolio
from ..models import types as models_types
from ..utils import ai_prompt as ai_prompt_utils
from ..utils import ai_reference as ai_reference_utils
from ..utils import cache, conv
from . import ai_helper, portfolio_budget, portfolio_verification

_PLAN_TASK = "REVIEW_PORTFOLIO_PLAN"
_RESEARCH_TASK = "REVIEW_PORTFOLIO_RESEARCH"
_ASSESS_TASK = "REVIEW_PORTFOLIO_ASSESS"
_TARGET_TASK = "REVIEW_PORTFOLIO_TARGET"
_ACTION_PLAN_TASK = "REVIEW_PORTFOLIO_ACTION_PLAN"

_PLAN_PROMPT = "portfolio_review_plan.txt"
_RESEARCH_PROMPT = "portfolio_review_research.txt"
_ASSESS_PROMPT = "portfolio_review_assessment.txt"
_TARGET_PROMPT = "portfolio_review_target.txt"
_ACTION_PLAN_PROMPT = "portfolio_review_action_plan.txt"

_PLAN_SCHEMA_NAME = "portfolio_review_plan"
_RESEARCH_SCHEMA_NAME = "portfolio_review_research"
_ASSESS_SCHEMA_NAME = "portfolio_review_assessment"
_TARGET_SCHEMA_NAME = "portfolio_review_target"
_ACTION_PLAN_SCHEMA_NAME = "portfolio_review_action_plan"

_PLAN_CACHE_NAMESPACE = "portfolio-review-plan-v1"
_RESEARCH_CACHE_NAMESPACE = "portfolio-review-research-v1"
_ASSESS_CACHE_NAMESPACE = "portfolio-review-assessment-v1"
_TARGET_CACHE_NAMESPACE = "portfolio-review-target-v1"
_ACTION_PLAN_CACHE_NAMESPACE = "portfolio-review-action-plan-v1"
_FINAL_CACHE_NAMESPACE = "portfolio-review-final-v1"
_PLAN_CACHE_TTL = 60 * 60
_ANALYSIS_CACHE_TTL = 30 * 60
_ACTION_CACHE_TTL = 5 * 60
_FINAL_CACHE_TTL = 5 * 60
_ALLOCATION_TOLERANCE = 0.01
_EXACT_ALLOCATION_TOLERANCE = 1e-6

_ResearchCategory = Literal[
    "Issuer",
    "Sector",
    "Macro",
    "Portfolio",
    "Liquidity",
    "Valuation",
    "Catalyst",
]
_RoleCategory = Literal[
    "CoreGrowth",
    "DefensiveIncome",
    "Diversifier",
    "Hedge",
    "Tactical",
    "CashReserve",
]

_ROLE_PREFIXES: dict[_RoleCategory, str] = {
    "CoreGrowth": "🚀",
    "DefensiveIncome": "🛡️",
    "Diversifier": "🧭",
    "Hedge": "🧱",
    "Tactical": "⚡",
    "CashReserve": "💵",
}
_RISK_LEVEL_ORDER: dict[models_review.PortfolioReviewRiskLevel, int] = {
    "Critical": 0,
    "High": 1,
    "Medium": 2,
    "Low": 3,
}
_SWING_PATTERN = re.compile(
    r"\b(?:swing(?:\s+trading)?|short[\s-]?term\s+trad(?:e|er|ing)|"
    r"days?[\s-]*(?:to|through)[\s-]*weeks?|multi[\s-]?day\s+trad(?:e|ing)|"
    r"trad(?:e|ing)\s+horizon(?:\s+of)?\s+\d+\s+(?:days?|weeks?))\b",
    re.IGNORECASE,
)
_LONG_TERM_PATTERN = re.compile(
    r"\b(?:long[\s-]?term|buy[\s-]?and[\s-]?hold|retirement|"
    r"multi[\s-]?year|hold(?:ing)?\s+horizon(?:\s+of)?\s+\d+\s+years?)\b",
    re.IGNORECASE,
)


class PortfolioReviewAIError(RuntimeError):
    pass


class _PortfolioReviewPlan(models_ai.StrictAIModel):
    portfolio_id: models_types.NonEmptyString = Field(max_length=128)
    strategy: models_review.PortfolioReviewStrategy
    budget: models_construction.PortfolioBudget
    objective: models_types.NonEmptyString = Field(max_length=4000)
    theme_interpretation: models_types.NonEmptyString = Field(max_length=4000)
    research_priorities: list[_ResearchCategory] = Field(min_length=1, max_length=7)
    strength_questions: list[Annotated[models_types.NonEmptyString, Field(max_length=1000)]] = Field(
        min_length=1,
        max_length=10,
    )
    risk_questions: list[Annotated[models_types.NonEmptyString, Field(max_length=1000)]] = Field(
        min_length=2,
        max_length=12,
    )
    holding_questions: list[Annotated[models_types.NonEmptyString, Field(max_length=1000)]] = Field(
        min_length=2,
        max_length=12,
    )
    target_design_questions: list[Annotated[models_types.NonEmptyString, Field(max_length=1000)]] = Field(
        min_length=2,
        max_length=12,
    )
    candidate_addition_queries: list[Annotated[models_types.NonEmptyString, Field(max_length=1000)]] = Field(
        max_length=5,
    )
    data_gaps: list[Annotated[models_types.NonEmptyString, Field(max_length=1000)]] = Field(
        max_length=20,
    )

    @model_validator(mode="after")
    def validate_plan(self) -> Self:
        for field_name in (
            "research_priorities",
            "strength_questions",
            "risk_questions",
            "holding_questions",
            "target_design_questions",
            "candidate_addition_queries",
        ):
            values = getattr(self, field_name)
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} must be unique")
        return self


class _PortfolioResearchSourceMetadata(models_ai.ReferenceSourceMetadata):
    id: models_types.NonEmptyString = Field(max_length=4000)
    accessed_at: datetime | None

    @model_validator(mode="after")
    def validate_temporary_id(self) -> Self:
        if ai_reference_utils.normalize_url(self.id) != ai_reference_utils.normalize_url(str(self.url)):
            raise ValueError("temporary source ID must equal its HTTPS URL")
        return self


class _PortfolioResearchClaim(models_ai.StrictAIModel):
    category: _ResearchCategory
    text: models_types.NonEmptyString = Field(max_length=4000)
    affected_tickers: list[str] = Field(min_length=1, max_length=50)
    reference_ids: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(
        min_length=1,
        max_length=6,
    )

    @field_validator("affected_tickers", mode="after")
    @classmethod
    def normalize_tickers(cls, value: list[str]) -> list[str]:
        normalized = [models_portfolio.normalize_canonical_ticker(ticker) for ticker in value]
        if len(normalized) != len(set(normalized)):
            raise ValueError("claim affected_tickers must be unique")
        return normalized

    @model_validator(mode="after")
    def validate_claim(self) -> Self:
        if len(self.reference_ids) != len(set(self.reference_ids)):
            raise ValueError("claim reference_ids must be unique")
        return self


class _PortfolioResearchAddition(models_ai.StrictAIModel):
    ticker: str = Field(min_length=1, max_length=models_portfolio.MAX_TICKER_LENGTH)
    company_name: str | None = Field(
        max_length=models_portfolio.MAX_COMPANY_NAME_LENGTH,
    )
    fit: models_types.NonEmptyString = Field(max_length=4000)
    key_risks: list[Annotated[models_types.NonEmptyString, Field(max_length=1000)]] = Field(
        min_length=1,
        max_length=8,
    )
    reference_ids: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(
        min_length=1,
        max_length=6,
    )

    @field_validator("ticker", mode="before")
    @classmethod
    def normalize_ticker(cls, value: object) -> object:
        return models_portfolio.normalize_canonical_ticker(value)

    @model_validator(mode="after")
    def validate_addition(self) -> Self:
        if len(self.reference_ids) != len(set(self.reference_ids)):
            raise ValueError("addition reference_ids must be unique")
        return self


class _PortfolioResearchResponse(models_ai.StrictAIModel):
    portfolio_id: models_types.NonEmptyString = Field(max_length=128)
    claims: list[_PortfolioResearchClaim] = Field(min_length=1, max_length=100)
    additions: list[_PortfolioResearchAddition] = Field(max_length=5)
    data_gaps: list[Annotated[models_types.NonEmptyString, Field(max_length=1000)]] = Field(
        max_length=20,
    )
    references: list[_PortfolioResearchSourceMetadata] = Field(min_length=1, max_length=100)


class _PortfolioResearchDraft(_PortfolioResearchResponse):
    @model_validator(mode="after")
    def validate_research(self) -> Self:
        addition_tickers = [addition.ticker for addition in self.additions]
        if len(addition_tickers) != len(set(addition_tickers)):
            raise ValueError("research addition tickers must be unique")
        ai_reference_utils.validate_reference_registry(self.references, self)
        return self


class _PortfolioResearch(_PortfolioResearchDraft):
    as_of: datetime
    references: list[models_ai.ReferenceSource] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_final_research(self) -> Self:
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("research as_of must be timezone-aware")
        return self


class _PortfolioStrengthDraft(models_ai.StrictAIModel):
    title: models_types.NonEmptyString = Field(max_length=200)
    analysis: models_types.NonEmptyString = Field(max_length=4000)
    affected_tickers: list[str] = Field(min_length=1, max_length=50)
    confidence: int = Field(ge=0, le=100)
    data_gaps: list[Annotated[models_types.NonEmptyString, Field(max_length=1000)]] = Field(
        max_length=10,
    )
    reference_ids: list[Annotated[models_types.NonEmptyString, Field(max_length=128)]] = Field(
        min_length=1,
        max_length=6,
    )

    @field_validator("affected_tickers", mode="after")
    @classmethod
    def normalize_tickers(cls, value: list[str]) -> list[str]:
        normalized = [models_portfolio.normalize_canonical_ticker(ticker) for ticker in value]
        if len(normalized) != len(set(normalized)):
            raise ValueError("strength affected_tickers must be unique")
        return normalized


class _PortfolioRiskDraft(models_ai.StrictAIModel):
    level: models_review.PortfolioReviewRiskLevel
    risk: models_types.NonEmptyString = Field(max_length=4000)
    impact: models_types.NonEmptyString = Field(max_length=4000)
    mitigation: models_types.NonEmptyString = Field(max_length=4000)
    affected_tickers: list[str] = Field(min_length=1, max_length=50)
    confidence: int = Field(ge=0, le=100)
    data_gaps: list[Annotated[models_types.NonEmptyString, Field(max_length=1000)]] = Field(
        max_length=10,
    )
    reference_ids: list[Annotated[models_types.NonEmptyString, Field(max_length=128)]] = Field(
        min_length=1,
        max_length=6,
    )

    @field_validator("affected_tickers", mode="after")
    @classmethod
    def normalize_tickers(cls, value: list[str]) -> list[str]:
        normalized = [models_portfolio.normalize_canonical_ticker(ticker) for ticker in value]
        if len(normalized) != len(set(normalized)):
            raise ValueError("risk affected_tickers must be unique")
        return normalized


class _PortfolioHoldingAssessmentDraft(models_ai.StrictAIModel):
    ticker: str = Field(min_length=1, max_length=models_portfolio.MAX_TICKER_LENGTH)
    role_category: _RoleCategory
    role_description: models_types.NonEmptyString = Field(max_length=900)
    thesis: models_types.NonEmptyString = Field(max_length=4000)
    strengths: list[Annotated[models_types.NonEmptyString, Field(max_length=1000)]] = Field(
        min_length=1,
        max_length=8,
    )
    risks: list[Annotated[models_types.NonEmptyString, Field(max_length=1000)]] = Field(
        min_length=1,
        max_length=8,
    )
    recommendation: models_review.PortfolioReviewHoldingRecommendation
    exit_reason: models_review.PortfolioReviewExitReason | None
    confidence: int = Field(ge=0, le=100)
    data_gaps: list[Annotated[models_types.NonEmptyString, Field(max_length=1000)]] = Field(
        max_length=10,
    )
    reference_ids: list[Annotated[models_types.NonEmptyString, Field(max_length=128)]] = Field(
        min_length=1,
        max_length=6,
    )

    @field_validator("ticker", mode="before")
    @classmethod
    def normalize_ticker(cls, value: object) -> object:
        return models_portfolio.normalize_canonical_ticker(value)

    @model_validator(mode="after")
    def validate_assessment(self) -> Self:
        if self.recommendation == "EXIT":
            if self.exit_reason is None:
                raise ValueError("EXIT holding assessment requires an exit reason")
        elif self.exit_reason is not None:
            raise ValueError("Only EXIT holding assessments can contain an exit reason")
        if len(self.reference_ids) != len(set(self.reference_ids)):
            raise ValueError("holding assessment reference_ids must be unique")
        return self


class _PortfolioAssessmentDraft(models_ai.StrictAIModel):
    portfolio_id: models_types.NonEmptyString = Field(max_length=128)
    summary: models_types.NonEmptyString = Field(max_length=4000)
    strengths: list[_PortfolioStrengthDraft] = Field(min_length=1, max_length=10)
    risks: list[_PortfolioRiskDraft] = Field(min_length=1, max_length=10)
    holding_reviews: list[_PortfolioHoldingAssessmentDraft] = Field(min_length=1, max_length=50)
    eligible_additions: list[str] = Field(max_length=5)
    overall_data_quality: models_types.DataQuality
    data_gaps: list[Annotated[models_types.NonEmptyString, Field(max_length=1000)]] = Field(
        max_length=20,
    )

    @field_validator("eligible_additions", mode="after")
    @classmethod
    def normalize_additions(cls, value: list[str]) -> list[str]:
        normalized = [models_portfolio.normalize_canonical_ticker(ticker) for ticker in value]
        if len(normalized) != len(set(normalized)):
            raise ValueError("eligible_additions must be unique")
        return normalized

    @model_validator(mode="after")
    def validate_assessment(self) -> Self:
        tickers = [review.ticker for review in self.holding_reviews]
        if len(tickers) != len(set(tickers)):
            raise ValueError("holding assessment tickers must be unique")
        risk_order = [_RISK_LEVEL_ORDER[risk.level] for risk in self.risks]
        if risk_order != sorted(risk_order):
            raise ValueError("assessment risks must be ordered from highest to lowest level")
        return self


class _PortfolioTargetPositionDraft(models_ai.StrictAIModel):
    ticker: str = Field(min_length=1, max_length=models_portfolio.MAX_TICKER_LENGTH)
    allocation: float = Field(gt=0, le=1, allow_inf_nan=False)
    role_category: _RoleCategory
    role_description: models_types.NonEmptyString = Field(max_length=900)
    rationale: models_types.NonEmptyString = Field(max_length=4000)
    reference_ids: list[Annotated[models_types.NonEmptyString, Field(max_length=128)]] = Field(
        min_length=1,
        max_length=6,
    )

    @field_validator("ticker", mode="before")
    @classmethod
    def normalize_ticker(cls, value: object) -> object:
        return models_portfolio.normalize_canonical_ticker(value)

    @model_validator(mode="after")
    def validate_position(self) -> Self:
        if len(self.reference_ids) != len(set(self.reference_ids)):
            raise ValueError("target position reference_ids must be unique")
        return self


class _PortfolioTargetDraft(models_ai.StrictAIModel):
    portfolio_id: models_types.NonEmptyString = Field(max_length=128)
    summary: models_types.NonEmptyString = Field(max_length=4000)
    positions: list[_PortfolioTargetPositionDraft] = Field(min_length=1, max_length=55)
    data_gaps: list[Annotated[models_types.NonEmptyString, Field(max_length=1000)]] = Field(
        max_length=20,
    )

    @model_validator(mode="after")
    def validate_target(self) -> Self:
        tickers = [position.ticker for position in self.positions]
        if len(tickers) != len(set(tickers)):
            raise ValueError("target position tickers must be unique")
        if abs(sum(position.allocation for position in self.positions) - 1.0) > _ALLOCATION_TOLERANCE:
            raise ValueError("target allocations must sum to one")
        return self


class _PortfolioActionReasoning(models_ai.StrictAIModel):
    action_id: str = Field(min_length=1, max_length=128)
    priority: int = Field(ge=1, le=70)
    reasoning: models_types.NonEmptyString = Field(max_length=4000)


class _PortfolioActionPlanDraft(models_ai.StrictAIModel):
    summary: models_types.NonEmptyString = Field(max_length=4000)
    actions: list[_PortfolioActionReasoning] = Field(min_length=1, max_length=70)

    @model_validator(mode="after")
    def validate_action_plan(self) -> Self:
        action_ids = [action.action_id for action in self.actions]
        if len(action_ids) != len(set(action_ids)):
            raise ValueError("action reasoning IDs must be unique")
        priorities = sorted(action.priority for action in self.actions)
        if priorities != list(range(1, len(self.actions) + 1)):
            raise ValueError("action priorities must be consecutive and start at one")
        return self


class _PortfolioActionCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_id: str
    action: models_review.PortfolioReviewActionType
    ticker: str
    company_name: str | None
    current_allocation: float = Field(ge=0, le=1, allow_inf_nan=False)
    target_allocation: float = Field(ge=0, le=1, allow_inf_nan=False)
    quantity: int | None = Field(ge=1)
    market_price: float | None = Field(gt=0, allow_inf_nan=False)
    estimated_amount: float | None = Field(gt=0, allow_inf_nan=False)
    instruction: str
    reference_ids: list[str]
    priority_group: Literal[0, 1, 2, 3, 4]
    priority_score: float


class _CalculatedActions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    budget: models_construction.PortfolioBudget
    cash_ledger: models_review.PortfolioReviewCashLedger
    candidates: list[_PortfolioActionCandidate] = Field(min_length=1, max_length=70)


async def ai_review_portfolio(
    portfolio: list[models_portfolio.PortfolioHolding],
    *,
    country: str,
    investor_theme: str,
    rebalance_plan: bool = False,
) -> models_review.PortfolioReview:
    """Verify and review an existing portfolio using structured, cached AI stages."""

    normalized_country = conv.country_to_iso2(country.strip())
    if not normalized_country:
        raise portfolio_verification.PortfolioInputError("Unsupported or unknown country")
    normalized_theme = investor_theme.strip()
    if not normalized_theme:
        raise portfolio_verification.PortfolioInputError("Investor theme must not be empty")
    strategy = extract_strategy(normalized_theme)

    active_positions = [position.model_copy(deep=True) for position in portfolio if position.num_shares > 0]
    if not active_positions:
        raise portfolio_verification.PortfolioInputError(
            "Portfolio review requires at least one positive-share position"
        )
    if any(not float(position.num_shares).is_integer() for position in active_positions):
        raise portfolio_verification.PortfolioInputError("Portfolio review supports whole-share holdings only")

    verified_portfolio = await portfolio_verification.verify_portfolio(
        active_positions,
        country=normalized_country,
    )
    snapshot = models_review.PortfolioReviewSnapshot.model_validate(verified_portfolio.model_dump())
    budget = portfolio_budget.extract_budget(
        normalized_theme,
        default_currency=snapshot.currency,
    )
    if budget.budget_type == "NotProvided":
        budget = portfolio_budget.infer_recurring_budget(
            verified_portfolio,
            rate=portfolio_budget.INFERRED_BUDGET_MIN_RATE,
        )
    if budget.currency != snapshot.currency:
        raise portfolio_verification.PortfolioInputError(
            f"Investment budget currency must match the {snapshot.currency} portfolio currency"
        )

    portfolio_id = cache.generate_key(
        "portfolio-review-id-v1",
        snapshot.model_dump_json(),
        normalized_theme,
        strategy,
    )
    plan = await _plan_portfolio(
        portfolio_id=portfolio_id,
        snapshot=snapshot,
        investor_theme=normalized_theme,
        strategy=strategy,
        budget=budget,
    )
    research = await _research_portfolio(
        portfolio_id=portfolio_id,
        snapshot=snapshot,
        investor_theme=normalized_theme,
        strategy=strategy,
        plan=plan,
    )
    assessment = await _assess_portfolio(
        portfolio_id=portfolio_id,
        snapshot=snapshot,
        investor_theme=normalized_theme,
        strategy=strategy,
        plan=plan,
        research=research,
    )
    target_draft = await _design_target(
        portfolio_id=portfolio_id,
        snapshot=snapshot,
        investor_theme=normalized_theme,
        strategy=strategy,
        plan=plan,
        research=research,
        assessment=assessment,
    )
    target_positions = _build_target_positions(
        snapshot=snapshot,
        research=research,
        assessment=assessment,
        target_draft=target_draft,
    )
    holding_reviews = _build_holding_reviews(
        snapshot=snapshot,
        assessment=assessment,
        target_positions=target_positions,
        strategy=strategy,
    )
    target_turnover = _calculate_target_turnover(snapshot, target_positions)
    major_rebalance_reasons = _major_rebalance_reasons(
        snapshot=snapshot,
        assessment=assessment,
        target_positions=target_positions,
        target_turnover=target_turnover,
    )
    rebalance_recommended: models_review.PortfolioReviewRebalanceFlag = "YES" if major_rebalance_reasons else "NO"
    should_build_actions = rebalance_plan or rebalance_recommended == "NO"

    verified_addition_quotes = None
    calculated_actions = None
    if should_build_actions:
        verified_addition_quotes = await _verify_addition_quotes(
            snapshot=snapshot,
            target_positions=target_positions,
        )
        budget, calculated_actions = _resolve_action_budget(
            verified_portfolio=verified_portfolio,
            snapshot=snapshot,
            target_positions=target_positions,
            holding_reviews=holding_reviews,
            verified_addition_quotes=verified_addition_quotes,
            budget=budget,
            strategy=strategy,
        )

    final_cache_key = _final_cache_key(
        snapshot=snapshot,
        investor_theme=normalized_theme,
        strategy=strategy,
        rebalance_requested=rebalance_plan,
        plan=plan,
        research=research,
        assessment=assessment,
        target_draft=target_draft,
        budget=budget,
        verified_addition_quotes=verified_addition_quotes,
        calculated_actions=calculated_actions,
    )
    cached_review = await cache.get(final_cache_key)
    if cached_review is not None:
        return _cached_review(cached_review)

    action_plan_draft = (
        await _create_action_plan(
            snapshot=snapshot,
            investor_theme=normalized_theme,
            strategy=strategy,
            assessment=assessment,
            target_positions=target_positions,
            calculated_actions=calculated_actions,
        )
        if calculated_actions is not None
        else None
    )
    review = _finalize_review(
        snapshot=snapshot,
        investor_theme=normalized_theme,
        strategy=strategy,
        rebalance_requested=rebalance_plan,
        rebalance_recommended=rebalance_recommended,
        major_rebalance_reasons=major_rebalance_reasons,
        budget=budget,
        plan=plan,
        research=research,
        assessment=assessment,
        target_draft=target_draft,
        target_positions=target_positions,
        holding_reviews=holding_reviews,
        target_turnover=target_turnover,
        calculated_actions=calculated_actions,
        action_plan_draft=action_plan_draft,
    )
    await cache.set(
        final_cache_key,
        review.model_dump(mode="json"),
        ttl=_FINAL_CACHE_TTL,
    )
    return review


def extract_strategy(investor_theme: str) -> models_review.PortfolioReviewStrategy:
    """Extract an explicit portfolio style, defaulting to LongTerm."""

    has_swing = bool(_SWING_PATTERN.search(investor_theme))
    has_long_term = bool(_LONG_TERM_PATTERN.search(investor_theme))
    if has_swing and has_long_term:
        raise portfolio_verification.PortfolioInputError(
            "Investor theme contains conflicting LongTerm and Swing strategy cues"
        )
    return "Swing" if has_swing else "LongTerm"


async def _plan_portfolio(
    *,
    portfolio_id: str,
    snapshot: models_review.PortfolioReviewSnapshot,
    investor_theme: str,
    strategy: models_review.PortfolioReviewStrategy,
    budget: models_construction.PortfolioBudget,
) -> _PortfolioReviewPlan:
    prompt = ai_prompt_utils.render_prompt(
        _PLAN_PROMPT,
        {
            "MARKET_DATE": date.today().isoformat(),
            "REVIEW_INPUT_JSON": _review_input_json(
                portfolio_id=portfolio_id,
                snapshot=snapshot,
                investor_theme=investor_theme,
                strategy=strategy,
                budget=budget,
            ),
        },
    )
    cache_key = _stage_cache_key(
        _PLAN_CACHE_NAMESPACE,
        prompt,
        _PortfolioReviewPlan,
        _PLAN_TASK,
    )
    cached_plan = await cache.get(cache_key)
    if cached_plan is not None:
        return _cached_plan(cached_plan)

    response = await _execute_stage(
        _PLAN_TASK,
        prompt,
        country=snapshot.country,
        response_model=_PortfolioReviewPlan,
        schema_name=_PLAN_SCHEMA_NAME,
        stage_name="planning",
    )
    try:
        plan = _PortfolioReviewPlan.model_validate_json(response.completion)
        if plan.portfolio_id != portfolio_id:
            raise ValueError("planning returned a different portfolio ID")
        if plan.strategy != strategy:
            raise ValueError("planning changed the deterministically extracted strategy")
        if plan.budget != budget:
            raise ValueError("planning changed the deterministically normalized budget")
    except (ValueError, ValidationError) as exc:
        raise PortfolioReviewAIError("Portfolio review planning returned invalid structured data") from exc

    await cache.set(cache_key, plan.model_dump(mode="json"), ttl=_PLAN_CACHE_TTL)
    return plan


async def _research_portfolio(
    *,
    portfolio_id: str,
    snapshot: models_review.PortfolioReviewSnapshot,
    investor_theme: str,
    strategy: models_review.PortfolioReviewStrategy,
    plan: _PortfolioReviewPlan,
) -> _PortfolioResearch:
    prompt = ai_prompt_utils.render_prompt(
        _RESEARCH_PROMPT,
        {
            "MARKET_DATE": date.today().isoformat(),
            "REVIEW_INPUT_JSON": _review_input_json(
                portfolio_id=portfolio_id,
                snapshot=snapshot,
                investor_theme=investor_theme,
                strategy=strategy,
                budget=plan.budget,
            ),
            "PLAN_JSON": plan.model_dump_json(),
        },
    )
    cache_key = _stage_cache_key(
        _RESEARCH_CACHE_NAMESPACE,
        prompt,
        _PortfolioResearchResponse,
        _RESEARCH_TASK,
    )
    cached_research = await cache.get(cache_key)
    if cached_research is not None:
        return _cached_research(cached_research)

    response = await _execute_stage(
        _RESEARCH_TASK,
        prompt,
        country=snapshot.country,
        response_model=_PortfolioResearchResponse,
        schema_name=_RESEARCH_SCHEMA_NAME,
        stage_name="research",
    )
    try:
        research_response = _PortfolioResearchResponse.model_validate_json(response.completion)
        if research_response.portfolio_id != portfolio_id:
            raise ValueError("research returned a different portfolio ID")
        repaired_research = _repair_research_references(research_response)
        _validate_research_coverage(repaired_research, snapshot)
        research = _finalize_research_references(
            repaired_research,
            response.citation_urls,
            accessed_at=datetime.now(UTC),
        )
    except (TypeError, ValueError, ValidationError) as exc:
        raise PortfolioReviewAIError("Portfolio review research returned invalid structured data") from exc

    await cache.set(cache_key, research.model_dump(mode="json"), ttl=_ANALYSIS_CACHE_TTL)
    return research


async def _assess_portfolio(
    *,
    portfolio_id: str,
    snapshot: models_review.PortfolioReviewSnapshot,
    investor_theme: str,
    strategy: models_review.PortfolioReviewStrategy,
    plan: _PortfolioReviewPlan,
    research: _PortfolioResearch,
) -> _PortfolioAssessmentDraft:
    prompt = ai_prompt_utils.render_prompt(
        _ASSESS_PROMPT,
        {
            "REVIEW_INPUT_JSON": _review_input_json(
                portfolio_id=portfolio_id,
                snapshot=snapshot,
                investor_theme=investor_theme,
                strategy=strategy,
                budget=plan.budget,
            ),
            "PLAN_JSON": plan.model_dump_json(),
            "RESEARCH_JSON": research.model_dump_json(),
        },
    )
    cache_key = _stage_cache_key(
        _ASSESS_CACHE_NAMESPACE,
        prompt,
        _PortfolioAssessmentDraft,
        _ASSESS_TASK,
    )
    cached_assessment = await cache.get(cache_key)
    if cached_assessment is not None:
        assessment = _cached_assessment(cached_assessment)
        try:
            _validate_assessment(assessment, snapshot, research, strategy=strategy)
        except ValueError as exc:
            raise RuntimeError("Portfolio review assessment cache contains an invalid value") from exc
        return assessment

    response = await _execute_stage(
        _ASSESS_TASK,
        prompt,
        country=snapshot.country,
        response_model=_PortfolioAssessmentDraft,
        schema_name=_ASSESS_SCHEMA_NAME,
        stage_name="assessment",
    )
    try:
        assessment = _PortfolioAssessmentDraft.model_validate_json(response.completion)
        if assessment.portfolio_id != portfolio_id:
            raise ValueError("assessment returned a different portfolio ID")
        _validate_assessment(assessment, snapshot, research, strategy=strategy)
    except (ValueError, ValidationError) as exc:
        raise PortfolioReviewAIError("Portfolio review assessment returned invalid structured data") from exc

    await cache.set(cache_key, assessment.model_dump(mode="json"), ttl=_ANALYSIS_CACHE_TTL)
    return assessment


async def _design_target(
    *,
    portfolio_id: str,
    snapshot: models_review.PortfolioReviewSnapshot,
    investor_theme: str,
    strategy: models_review.PortfolioReviewStrategy,
    plan: _PortfolioReviewPlan,
    research: _PortfolioResearch,
    assessment: _PortfolioAssessmentDraft,
) -> _PortfolioTargetDraft:
    prompt = ai_prompt_utils.render_prompt(
        _TARGET_PROMPT,
        {
            "REVIEW_INPUT_JSON": _review_input_json(
                portfolio_id=portfolio_id,
                snapshot=snapshot,
                investor_theme=investor_theme,
                strategy=strategy,
                budget=plan.budget,
            ),
            "PLAN_JSON": plan.model_dump_json(),
            "RESEARCH_JSON": research.model_dump_json(),
            "ASSESSMENT_JSON": assessment.model_dump_json(),
        },
    )
    cache_key = _stage_cache_key(
        _TARGET_CACHE_NAMESPACE,
        prompt,
        _PortfolioTargetDraft,
        _TARGET_TASK,
    )
    cached_target = await cache.get(cache_key)
    if cached_target is not None:
        target = _cached_target(cached_target)
        try:
            _validate_target(target, snapshot, research, assessment)
        except ValueError as exc:
            raise RuntimeError("Portfolio review target cache contains an invalid value") from exc
        return target

    response = await _execute_stage(
        _TARGET_TASK,
        prompt,
        country=snapshot.country,
        response_model=_PortfolioTargetDraft,
        schema_name=_TARGET_SCHEMA_NAME,
        stage_name="target design",
    )
    try:
        target = _PortfolioTargetDraft.model_validate_json(response.completion)
        if target.portfolio_id != portfolio_id:
            raise ValueError("target design returned a different portfolio ID")
        _validate_target(target, snapshot, research, assessment)
    except (ValueError, ValidationError) as exc:
        raise PortfolioReviewAIError("Portfolio review target design returned invalid structured data") from exc

    await cache.set(cache_key, target.model_dump(mode="json"), ttl=_ANALYSIS_CACHE_TTL)
    return target


async def _create_action_plan(
    *,
    snapshot: models_review.PortfolioReviewSnapshot,
    investor_theme: str,
    strategy: models_review.PortfolioReviewStrategy,
    assessment: _PortfolioAssessmentDraft,
    target_positions: list[models_review.PortfolioReviewTargetPosition],
    calculated_actions: _CalculatedActions,
) -> _PortfolioActionPlanDraft:
    prompt_actions = [
        candidate.model_dump(
            mode="json",
            exclude={"priority_group", "priority_score"},
        )
        for candidate in calculated_actions.candidates
    ]
    prompt = ai_prompt_utils.render_prompt(
        _ACTION_PLAN_PROMPT,
        {
            "REVIEW_INPUT_JSON": json.dumps(
                {
                    "investor_theme": investor_theme,
                    "strategy": strategy,
                    "snapshot": snapshot.model_dump(mode="json"),
                    "budget": calculated_actions.budget.model_dump(mode="json"),
                },
                sort_keys=True,
            ),
            "ASSESSMENT_JSON": assessment.model_dump_json(),
            "TARGET_JSON": json.dumps(
                [position.model_dump(mode="json") for position in target_positions],
                sort_keys=True,
            ),
            "ACTION_CANDIDATES_JSON": json.dumps(
                {
                    "cash_ledger": calculated_actions.cash_ledger.model_dump(mode="json"),
                    "actions": prompt_actions,
                },
                sort_keys=True,
            ),
        },
    )
    cache_key = _stage_cache_key(
        _ACTION_PLAN_CACHE_NAMESPACE,
        prompt,
        _PortfolioActionPlanDraft,
        _ACTION_PLAN_TASK,
    )
    cached_draft = await cache.get(cache_key)
    if cached_draft is not None:
        draft = _cached_action_plan(cached_draft)
        try:
            _validate_action_plan_draft(draft, calculated_actions.candidates)
        except ValueError as exc:
            raise RuntimeError("Portfolio review action-plan cache contains an invalid value") from exc
        return draft

    response = await _execute_stage(
        _ACTION_PLAN_TASK,
        prompt,
        country=snapshot.country,
        response_model=_PortfolioActionPlanDraft,
        schema_name=_ACTION_PLAN_SCHEMA_NAME,
        stage_name="action planning",
    )
    try:
        draft = _PortfolioActionPlanDraft.model_validate_json(response.completion)
        _validate_action_plan_draft(draft, calculated_actions.candidates)
    except (ValueError, ValidationError) as exc:
        raise PortfolioReviewAIError("Portfolio review action planning returned invalid structured data") from exc

    await cache.set(cache_key, draft.model_dump(mode="json"), ttl=_ACTION_CACHE_TTL)
    return draft


async def _execute_stage(
    task_id: str,
    prompt: str,
    *,
    country: str,
    response_model: type[models_ai.StrictAIModel],
    schema_name: str,
    stage_name: str,
) -> ai_helper.LLMResponse:
    try:
        response = await ai_helper.ai_exec_task(
            task_id,
            prompt,
            country=country,
            response_json_schema=response_model.model_json_schema(),
            schema_name=schema_name,
        )
    except (OSError, ValueError, openai.APIError) as exc:
        logging.exception("[Portfolio Review] %s provider call failed.", stage_name.capitalize())
        raise PortfolioReviewAIError(f"Portfolio review {stage_name} provider failed") from exc
    if response.is_error:
        logging.error(
            "[Portfolio Review] %s failed: %s",
            stage_name.capitalize(),
            response.error_msg,
        )
        raise PortfolioReviewAIError(f"Portfolio review {stage_name} failed")
    return response


def _repair_research_references(
    research: _PortfolioResearchResponse,
) -> _PortfolioResearchDraft:
    research_data = research.model_dump()
    registry_ids = {reference.id for reference in research.references}
    missing_ids: set[str] = set()
    dropped_claims = 0
    dropped_additions = 0

    repaired_claims = []
    for claim in research_data["claims"]:
        unknown_ids = set(claim["reference_ids"]) - registry_ids
        missing_ids.update(unknown_ids)
        valid_ids = [reference_id for reference_id in claim["reference_ids"] if reference_id in registry_ids]
        if not valid_ids:
            dropped_claims += 1
            continue
        claim["reference_ids"] = list(dict.fromkeys(valid_ids))
        repaired_claims.append(claim)
    research_data["claims"] = repaired_claims

    repaired_additions = []
    for addition in research_data["additions"]:
        unknown_ids = set(addition["reference_ids"]) - registry_ids
        missing_ids.update(unknown_ids)
        valid_ids = [reference_id for reference_id in addition["reference_ids"] if reference_id in registry_ids]
        if not valid_ids:
            dropped_additions += 1
            continue
        addition["reference_ids"] = list(dict.fromkeys(valid_ids))
        repaired_additions.append(addition)
    research_data["additions"] = repaired_additions

    used_ids = ai_reference_utils.collect_reference_ids(research_data)
    research_data["references"] = [
        reference for reference in research_data["references"] if reference["id"] in used_ids
    ]
    if missing_ids or dropped_claims or dropped_additions:
        missing_text = ", ".join(sorted(missing_ids)) or "none"
        warning = f"Ignored missing source IDs: {missing_text}."
        if dropped_claims:
            warning += f" Removed {dropped_claims} unsupported claim(s)."
        if dropped_additions:
            warning += f" Removed {dropped_additions} unsupported addition candidate(s)."
        research_data["data_gaps"] = [*research_data["data_gaps"][:19], warning]
        logging.warning("[Portfolio Review] %s", warning)
    return _PortfolioResearchDraft.model_validate(research_data)


def _validate_research_coverage(
    research: _PortfolioResearchDraft,
    snapshot: models_review.PortfolioReviewSnapshot,
) -> None:
    current_tickers = {holding.ticker for holding in snapshot.holdings}
    claim_tickers = {ticker for claim in research.claims for ticker in claim.affected_tickers}
    unknown_claim_tickers = claim_tickers - current_tickers
    if unknown_claim_tickers:
        raise ValueError(f"research claims contain unknown current tickers: {sorted(unknown_claim_tickers)}")
    missing_tickers = current_tickers - claim_tickers
    if missing_tickers:
        raise ValueError(f"research did not cover current tickers: {sorted(missing_tickers)}")
    addition_tickers = {addition.ticker for addition in research.additions}
    duplicates = current_tickers & addition_tickers
    if duplicates:
        raise ValueError(f"research additions duplicate current holdings: {sorted(duplicates)}")


def _finalize_research_references(
    research: _PortfolioResearchDraft,
    citation_urls: list[str],
    *,
    accessed_at: datetime,
) -> _PortfolioResearch:
    canonicalized = ai_reference_utils.canonicalize_reference_sources(
        research.references,
        citation_urls,
        accessed_at=accessed_at,
    )
    research_data = ai_reference_utils.remap_reference_ids(research, canonicalized.id_map)
    if not isinstance(research_data, dict):
        raise TypeError("Remapped portfolio review research must be an object")
    research_data["as_of"] = accessed_at
    research_data["references"] = [reference.model_dump(mode="python") for reference in canonicalized.references]
    return _PortfolioResearch.model_validate(research_data)


def _validate_assessment(
    assessment: _PortfolioAssessmentDraft,
    snapshot: models_review.PortfolioReviewSnapshot,
    research: _PortfolioResearch,
    *,
    strategy: models_review.PortfolioReviewStrategy,
) -> None:
    current_tickers = {holding.ticker for holding in snapshot.holdings}
    assessment_tickers = {review.ticker for review in assessment.holding_reviews}
    if assessment_tickers != current_tickers or len(assessment.holding_reviews) != len(current_tickers):
        raise ValueError("assessment must review every current holding exactly once")

    research_reference_ids = {reference.id for reference in research.references}
    unknown_reference_ids = ai_reference_utils.collect_reference_ids(assessment) - research_reference_ids
    if unknown_reference_ids:
        raise ValueError(f"assessment contains unknown reference IDs: {sorted(unknown_reference_ids)}")

    for strength in assessment.strengths:
        unknown_tickers = set(strength.affected_tickers) - current_tickers
        if unknown_tickers:
            raise ValueError(f"assessment strength contains unknown tickers: {sorted(unknown_tickers)}")
    for risk in assessment.risks:
        unknown_tickers = set(risk.affected_tickers) - current_tickers
        if unknown_tickers:
            raise ValueError(f"assessment risk contains unknown tickers: {sorted(unknown_tickers)}")

    evidence_by_ticker = _research_reference_ids_by_ticker(research)
    for review in assessment.holding_reviews:
        unsupported_ids = set(review.reference_ids) - evidence_by_ticker[review.ticker]
        if unsupported_ids:
            raise ValueError(
                f"holding assessment {review.ticker} contains unsupported reference IDs: {sorted(unsupported_ids)}"
            )
        if strategy == "LongTerm" and review.recommendation == "TRIM":
            raise ValueError("LongTerm assessment cannot recommend TRIM")
        if (
            strategy == "LongTerm"
            and review.recommendation == "EXIT"
            and review.exit_reason
            not in {
                "CriticalRisk",
                "StructuralChange",
            }
        ):
            raise ValueError("LongTerm EXIT requires a critical-risk or structural-change reason")

    researched_additions = {addition.ticker for addition in research.additions}
    unknown_additions = set(assessment.eligible_additions) - researched_additions
    if unknown_additions:
        raise ValueError(f"assessment contains unresearched additions: {sorted(unknown_additions)}")


def _validate_target(
    target: _PortfolioTargetDraft,
    snapshot: models_review.PortfolioReviewSnapshot,
    research: _PortfolioResearch,
    assessment: _PortfolioAssessmentDraft,
) -> None:
    current_tickers = {holding.ticker for holding in snapshot.holdings}
    assessment_by_ticker = {review.ticker: review for review in assessment.holding_reviews}
    expected_retained = {ticker for ticker, review in assessment_by_ticker.items() if review.recommendation != "EXIT"}
    exited = current_tickers - expected_retained
    target_tickers = {position.ticker for position in target.positions}
    if target_tickers & exited:
        raise ValueError("target retained a holding assessed as EXIT")
    if not expected_retained.issubset(target_tickers):
        raise ValueError("target omitted a current holding without validated EXIT intent")

    introduced = target_tickers - current_tickers
    unknown_additions = introduced - set(assessment.eligible_additions)
    if unknown_additions:
        raise ValueError(f"target contains ineligible additions: {sorted(unknown_additions)}")

    evidence_by_ticker = _research_reference_ids_by_ticker(research)
    additions = {addition.ticker: addition for addition in research.additions}
    for position in target.positions:
        if position.ticker in current_tickers:
            supported_ids = evidence_by_ticker[position.ticker]
            if position.role_category != assessment_by_ticker[position.ticker].role_category:
                raise ValueError("target changed the assessed role category for a current holding")
        else:
            supported_ids = set(additions[position.ticker].reference_ids)
        unsupported_ids = set(position.reference_ids) - supported_ids
        if unsupported_ids:
            raise ValueError(
                f"target position {position.ticker} contains unsupported reference IDs: {sorted(unsupported_ids)}"
            )


def _research_reference_ids_by_ticker(research: _PortfolioResearch) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for claim in research.claims:
        for ticker in claim.affected_tickers:
            result.setdefault(ticker, set()).update(claim.reference_ids)
    return result


def _build_target_positions(
    *,
    snapshot: models_review.PortfolioReviewSnapshot,
    research: _PortfolioResearch,
    assessment: _PortfolioAssessmentDraft,
    target_draft: _PortfolioTargetDraft,
) -> list[models_review.PortfolioReviewTargetPosition]:
    _validate_target(target_draft, snapshot, research, assessment)
    current = {holding.ticker: holding for holding in snapshot.holdings}
    additions = {addition.ticker: addition for addition in research.additions}
    allocation_total = sum(position.allocation for position in target_draft.positions)
    return [
        models_review.PortfolioReviewTargetPosition(
            ticker=position.ticker,
            company_name=(
                current[position.ticker].company_name
                if position.ticker in current
                else additions[position.ticker].company_name
            ),
            current_allocation=(current[position.ticker].current_allocation if position.ticker in current else 0.0),
            target_allocation=position.allocation / allocation_total,
            role=_render_role(position.role_category, position.role_description),
            rationale=position.rationale,
            reference_ids=position.reference_ids,
        )
        for position in target_draft.positions
    ]


def _build_holding_reviews(
    *,
    snapshot: models_review.PortfolioReviewSnapshot,
    assessment: _PortfolioAssessmentDraft,
    target_positions: list[models_review.PortfolioReviewTargetPosition],
    strategy: models_review.PortfolioReviewStrategy,
) -> list[models_review.PortfolioHoldingReview]:
    assessment_by_ticker = {review.ticker: review for review in assessment.holding_reviews}
    targets = {position.ticker: position for position in target_positions}
    result = []
    for holding in snapshot.holdings:
        draft = assessment_by_ticker[holding.ticker]
        target = targets.get(holding.ticker)
        recommendation = _holding_recommendation(
            strategy=strategy,
            current_allocation=holding.current_allocation,
            target_allocation=target.target_allocation if target else 0.0,
            exit_reason=draft.exit_reason,
        )
        result.append(
            models_review.PortfolioHoldingReview(
                ticker=holding.ticker,
                company_name=holding.company_name,
                role=_render_role(draft.role_category, draft.role_description),
                current_allocation=holding.current_allocation,
                target_allocation=target.target_allocation if target else 0.0,
                thesis=draft.thesis,
                strengths=draft.strengths,
                risks=draft.risks,
                recommendation=recommendation,
                exit_reason=draft.exit_reason if recommendation == "EXIT" else None,
                confidence=draft.confidence,
                data_gaps=draft.data_gaps,
                reference_ids=draft.reference_ids,
            )
        )
    return result


def _holding_recommendation(
    *,
    strategy: models_review.PortfolioReviewStrategy,
    current_allocation: float,
    target_allocation: float,
    exit_reason: models_review.PortfolioReviewExitReason | None,
) -> models_review.PortfolioReviewHoldingRecommendation:
    if exit_reason is not None:
        return "EXIT"
    if target_allocation >= current_allocation - _EXACT_ALLOCATION_TOLERANCE:
        return "BUY_MORE"
    if strategy == "Swing" and target_allocation < current_allocation - _EXACT_ALLOCATION_TOLERANCE:
        return "TRIM"
    return "HOLD"


def _render_role(category: _RoleCategory, description: str) -> str:
    normalized_description = description.strip()
    return f"{_ROLE_PREFIXES[category]} {normalized_description}"


def _calculate_target_turnover(
    snapshot: models_review.PortfolioReviewSnapshot,
    target_positions: list[models_review.PortfolioReviewTargetPosition],
) -> float:
    current = {holding.ticker: holding.current_allocation for holding in snapshot.holdings}
    target = {position.ticker: position.target_allocation for position in target_positions}
    return 0.5 * sum(abs(target.get(ticker, 0.0) - current.get(ticker, 0.0)) for ticker in set(current) | set(target))


def _major_rebalance_reasons(
    *,
    snapshot: models_review.PortfolioReviewSnapshot,
    assessment: _PortfolioAssessmentDraft,
    target_positions: list[models_review.PortfolioReviewTargetPosition],
    target_turnover: float,
) -> list[str]:
    current_tickers = {holding.ticker for holding in snapshot.holdings}
    target_tickers = {position.ticker for position in target_positions}
    assessment_by_ticker = {review.ticker: review for review in assessment.holding_reviews}
    reasons = [
        (
            f"{ticker} requires EXIT because the validated assessment identified "
            f"{assessment_by_ticker[ticker].exit_reason}."
        )
        for ticker in sorted(current_tickers - target_tickers)
    ]
    introduced = sorted(target_tickers - current_tickers)
    if introduced:
        reasons.append(f"The validated target introduces new holding(s): {', '.join(introduced)}.")
    if target_turnover + _EXACT_ALLOCATION_TOLERANCE >= models_review.MAJOR_REBALANCE_TURNOVER:
        reasons.append(f"One-way target turnover is {target_turnover:.1%}, meeting the 20% major-rebalance threshold.")
    return reasons


async def _verify_addition_quotes(
    *,
    snapshot: models_review.PortfolioReviewSnapshot,
    target_positions: list[models_review.PortfolioReviewTargetPosition],
) -> portfolio_verification.VerifiedSecurityQuotes | None:
    current_tickers = {holding.ticker for holding in snapshot.holdings}
    addition_tickers = [position.ticker for position in target_positions if position.ticker not in current_tickers]
    if not addition_tickers:
        return None
    try:
        quotes = await portfolio_verification.verify_security_quotes(
            addition_tickers,
            country=snapshot.country,
        )
        if {quote.ticker for quote in quotes.securities} != set(addition_tickers):
            raise ValueError("verified addition quotes do not match target additions")
        if quotes.currency != snapshot.currency:
            raise ValueError("target additions do not use the portfolio currency")
        return quotes
    except (
        portfolio_verification.PortfolioInputError,
        portfolio_verification.PortfolioVerificationError,
        ValueError,
    ) as exc:
        raise PortfolioReviewAIError("Portfolio review target-price verification failed") from exc


def _resolve_action_budget(
    *,
    verified_portfolio: portfolio_verification.VerifiedPortfolio,
    snapshot: models_review.PortfolioReviewSnapshot,
    target_positions: list[models_review.PortfolioReviewTargetPosition],
    holding_reviews: list[models_review.PortfolioHoldingReview],
    verified_addition_quotes: portfolio_verification.VerifiedSecurityQuotes | None,
    budget: models_construction.PortfolioBudget,
    strategy: models_review.PortfolioReviewStrategy,
) -> tuple[models_construction.PortfolioBudget, _CalculatedActions]:
    calculated = _calculate_actions(
        snapshot=snapshot,
        target_positions=target_positions,
        holding_reviews=holding_reviews,
        verified_addition_quotes=verified_addition_quotes,
        budget=budget,
        strategy=strategy,
    )
    if not budget.is_inferred or any(
        candidate.action in {"BUY_MORE", "INTRODUCE"} for candidate in calculated.candidates
    ):
        return budget, calculated

    maximum_budget = portfolio_budget.infer_recurring_budget(
        verified_portfolio,
        rate=portfolio_budget.INFERRED_BUDGET_MAX_RATE,
    )
    maximum_calculated = _calculate_actions(
        snapshot=snapshot,
        target_positions=target_positions,
        holding_reviews=holding_reviews,
        verified_addition_quotes=verified_addition_quotes,
        budget=maximum_budget,
        strategy=strategy,
    )
    if any(candidate.action in {"BUY_MORE", "INTRODUCE"} for candidate in maximum_calculated.candidates):
        return maximum_budget, maximum_calculated
    return budget, calculated


def _calculate_actions(
    *,
    snapshot: models_review.PortfolioReviewSnapshot,
    target_positions: list[models_review.PortfolioReviewTargetPosition],
    holding_reviews: list[models_review.PortfolioHoldingReview],
    verified_addition_quotes: portfolio_verification.VerifiedSecurityQuotes | None,
    budget: models_construction.PortfolioBudget,
    strategy: models_review.PortfolioReviewStrategy,
) -> _CalculatedActions:
    if budget.amount is None:
        raise ValueError("Portfolio review actions require a budget amount")

    current = {holding.ticker: holding for holding in snapshot.holdings}
    targets = {position.ticker: position for position in target_positions}
    reviews = {review.ticker: review for review in holding_reviews}
    addition_quotes = {
        quote.ticker: quote for quote in (verified_addition_quotes.securities if verified_addition_quotes else [])
    }
    prices = {
        **{ticker: Decimal(str(holding.market_price)) for ticker, holding in current.items()},
        **{ticker: Decimal(str(quote.market_price)) for ticker, quote in addition_quotes.items()},
    }
    missing_prices = set(targets) - set(prices)
    if missing_prices:
        raise ValueError(f"Missing verified prices for target tickers: {sorted(missing_prices)}")

    budget_amount = Decimal(str(budget.amount))
    final_portfolio_value = Decimal(str(snapshot.total_market_value)) + budget_amount
    target_values = {
        ticker: Decimal(str(position.target_allocation)) * final_portfolio_value for ticker, position in targets.items()
    }
    post_sale_values = {ticker: Decimal(str(holding.market_value)) for ticker, holding in current.items()}
    candidates: dict[str, _PortfolioActionCandidate] = {}
    sale_proceeds = Decimal("0")

    for ticker in sorted(set(current) - set(targets)):
        holding = current[ticker]
        quantity = int(holding.num_shares)
        estimated_amount = Decimal(quantity) * prices[ticker]
        sale_proceeds += estimated_amount
        candidates[ticker] = _action_candidate(
            action="EXIT",
            ticker=ticker,
            company_name=holding.company_name,
            current_allocation=holding.current_allocation,
            target_allocation=0.0,
            quantity=quantity,
            market_price=prices[ticker],
            estimated_amount=estimated_amount,
            instruction=f"SELL ALL {quantity} whole shares of {ticker}.",
            reference_ids=reviews[ticker].reference_ids,
            priority_group=0,
            priority_score=holding.market_value,
        )
        post_sale_values[ticker] = Decimal("0")

    if strategy == "Swing":
        for ticker in sorted(set(current) & set(targets)):
            holding = current[ticker]
            excess_value = post_sale_values[ticker] - target_values[ticker]
            if excess_value <= 0:
                continue
            quantity = int((excess_value / prices[ticker]).to_integral_value(rounding=ROUND_FLOOR))
            quantity = min(quantity, int(holding.num_shares) - 1)
            if quantity <= 0:
                continue
            estimated_amount = Decimal(quantity) * prices[ticker]
            sale_proceeds += estimated_amount
            post_sale_values[ticker] -= estimated_amount
            candidates[ticker] = _action_candidate(
                action="TRIM",
                ticker=ticker,
                company_name=holding.company_name,
                current_allocation=holding.current_allocation,
                target_allocation=targets[ticker].target_allocation,
                quantity=quantity,
                market_price=prices[ticker],
                estimated_amount=estimated_amount,
                instruction=f"SELL {quantity} whole shares of {ticker}.",
                reference_ids=targets[ticker].reference_ids,
                priority_group=1,
                priority_score=float(excess_value),
            )

    available_cash = budget_amount + sale_proceeds
    desired_purchases = {}
    for ticker, target in targets.items():
        if ticker in candidates:
            continue
        if (
            strategy == "LongTerm"
            and ticker in current
            and target.target_allocation < current[ticker].current_allocation - _EXACT_ALLOCATION_TOLERANCE
        ):
            desired_purchases[ticker] = Decimal("0")
            continue
        desired_purchases[ticker] = max(
            target_values[ticker] - post_sale_values.get(ticker, Decimal("0")),
            Decimal("0"),
        )
    desired_purchases = {ticker: amount for ticker, amount in desired_purchases.items() if amount > 0}
    if desired_purchases:
        desired_total = sum(desired_purchases.values(), Decimal("0"))
        allocation_amounts = (
            {ticker: amount * available_cash / desired_total for ticker, amount in desired_purchases.items()}
            if desired_total > available_cash
            else desired_purchases
        )
        quantities, purchase_spend = portfolio_budget.allocate_whole_shares(
            available_cash,
            desired_amounts=allocation_amounts,
            prices={ticker: prices[ticker] for ticker in desired_purchases},
        )
    else:
        quantities, purchase_spend = {}, Decimal("0")

    for ticker, target in targets.items():
        if ticker in candidates:
            continue
        quantity = quantities.get(ticker, 0)
        is_current = ticker in current
        current_allocation = current[ticker].current_allocation if is_current else 0.0
        company_name = current[ticker].company_name if is_current else addition_quotes[ticker].company_name
        if quantity > 0:
            action: models_review.PortfolioReviewActionType = "BUY_MORE" if is_current else "INTRODUCE"
            estimated_amount = Decimal(quantity) * prices[ticker]
            instruction = (
                f"BUY {quantity} additional whole shares of {ticker}."
                if is_current
                else f"BUY {quantity} whole shares to introduce {ticker}."
            )
            candidates[ticker] = _action_candidate(
                action=action,
                ticker=ticker,
                company_name=company_name,
                current_allocation=current_allocation,
                target_allocation=target.target_allocation,
                quantity=quantity,
                market_price=prices[ticker],
                estimated_amount=estimated_amount,
                instruction=instruction,
                reference_ids=target.reference_ids,
                priority_group=2,
                priority_score=float(desired_purchases[ticker]),
            )
        elif ticker in desired_purchases:
            candidates[ticker] = _action_candidate(
                action="ACCUMULATE",
                ticker=ticker,
                company_name=company_name,
                current_allocation=current_allocation,
                target_allocation=target.target_allocation,
                quantity=None,
                market_price=prices[ticker],
                estimated_amount=None,
                instruction=f"Reserve cash until one whole share of {ticker} is affordable.",
                reference_ids=target.reference_ids,
                priority_group=3,
                priority_score=float(desired_purchases[ticker]),
            )
        else:
            held_quantity = int(current[ticker].num_shares)
            candidates[ticker] = _action_candidate(
                action="HOLD",
                ticker=ticker,
                company_name=company_name,
                current_allocation=current_allocation,
                target_allocation=target.target_allocation,
                quantity=None,
                market_price=prices[ticker],
                estimated_amount=None,
                instruction=f"HOLD the current {held_quantity} whole shares of {ticker}.",
                reference_ids=target.reference_ids,
                priority_group=4,
                priority_score=current[ticker].market_value,
            )

    ordered_candidates = sorted(
        candidates.values(),
        key=lambda candidate: (
            candidate.priority_group,
            -candidate.priority_score,
            candidate.ticker,
        ),
    )
    ledger = models_review.PortfolioReviewCashLedger(
        new_money_budget=portfolio_budget.round_money(budget_amount),
        estimated_sale_proceeds=portfolio_budget.round_money(sale_proceeds),
        purchase_spend=portfolio_budget.round_money(purchase_spend),
        unallocated_cash=portfolio_budget.round_money(available_cash - purchase_spend),
    )
    return _CalculatedActions(
        budget=budget,
        cash_ledger=ledger,
        candidates=ordered_candidates,
    )


def _action_candidate(
    *,
    action: models_review.PortfolioReviewActionType,
    ticker: str,
    company_name: str | None,
    current_allocation: float,
    target_allocation: float,
    quantity: int | None,
    market_price: Decimal | None,
    estimated_amount: Decimal | None,
    instruction: str,
    reference_ids: list[str],
    priority_group: Literal[0, 1, 2, 3, 4],
    priority_score: float,
) -> _PortfolioActionCandidate:
    return _PortfolioActionCandidate(
        action_id=f"{action.lower()}:{ticker}",
        action=action,
        ticker=ticker,
        company_name=company_name,
        current_allocation=current_allocation,
        target_allocation=target_allocation,
        quantity=quantity,
        market_price=float(market_price) if market_price is not None else None,
        estimated_amount=(portfolio_budget.round_money(estimated_amount) if estimated_amount is not None else None),
        instruction=instruction,
        reference_ids=reference_ids,
        priority_group=priority_group,
        priority_score=priority_score,
    )


def _validate_action_plan_draft(
    draft: _PortfolioActionPlanDraft,
    candidates: list[_PortfolioActionCandidate],
) -> None:
    candidate_ids = {candidate.action_id for candidate in candidates}
    response_ids = {action.action_id for action in draft.actions}
    if response_ids != candidate_ids or len(draft.actions) != len(candidate_ids):
        raise ValueError("action plan did not preserve the calculated action set")
    candidate_by_id = {candidate.action_id: candidate for candidate in candidates}
    ordered_groups = [
        candidate_by_id[action.action_id].priority_group
        for action in sorted(draft.actions, key=lambda item: item.priority)
    ]
    if ordered_groups != sorted(ordered_groups):
        raise ValueError("action plan violated fixed action-category priority")


def _finalize_review(
    *,
    snapshot: models_review.PortfolioReviewSnapshot,
    investor_theme: str,
    strategy: models_review.PortfolioReviewStrategy,
    rebalance_requested: bool,
    rebalance_recommended: models_review.PortfolioReviewRebalanceFlag,
    major_rebalance_reasons: list[str],
    budget: models_construction.PortfolioBudget,
    plan: _PortfolioReviewPlan,
    research: _PortfolioResearch,
    assessment: _PortfolioAssessmentDraft,
    target_draft: _PortfolioTargetDraft,
    target_positions: list[models_review.PortfolioReviewTargetPosition],
    holding_reviews: list[models_review.PortfolioHoldingReview],
    target_turnover: float,
    calculated_actions: _CalculatedActions | None,
    action_plan_draft: _PortfolioActionPlanDraft | None,
) -> models_review.PortfolioReview:
    strengths = [
        models_review.PortfolioReviewStrength.model_validate(strength.model_dump()) for strength in assessment.strengths
    ]
    risks = [models_review.PortfolioReviewRisk.model_validate(risk.model_dump()) for risk in assessment.risks]
    action_plan = _build_action_plan(
        rebalance_recommended=rebalance_recommended,
        calculated_actions=calculated_actions,
        action_plan_draft=action_plan_draft,
    )

    used_reference_ids = ai_reference_utils.collect_reference_ids(
        {
            "strengths": strengths,
            "risks": risks,
            "holding_reviews": holding_reviews,
            "target_portfolio": target_positions,
            "action_plan": action_plan,
        }
    )
    references = [reference for reference in research.references if reference.id in used_reference_ids]
    unverified_count = sum(not reference.is_verified for reference in references)
    validation_warnings = (
        [f"{unverified_count} cited research source(s) could not be provider-verified."] if unverified_count else []
    )
    inferred_budget_gaps = [f"Action budget assumption: {budget.source_text}"] if budget.is_inferred else []
    data_gaps = list(
        dict.fromkeys(
            [
                *snapshot.data_gaps,
                *inferred_budget_gaps,
                *plan.data_gaps,
                *research.data_gaps,
                *assessment.data_gaps,
                *target_draft.data_gaps,
            ]
        )
    )[:20]
    try:
        return models_review.PortfolioReview(
            as_of=datetime.now(UTC),
            review_status="CompleteWithWarnings" if validation_warnings else "Complete",
            strategy=strategy,
            country=snapshot.country,
            investor_theme=investor_theme,
            snapshot=snapshot,
            budget=budget,
            summary=assessment.summary,
            strengths=strengths,
            risks=risks,
            holding_reviews=holding_reviews,
            target_portfolio=target_positions,
            target_turnover=target_turnover,
            rebalance_requested=rebalance_requested,
            rebalance_recommended=rebalance_recommended,
            major_rebalance_reasons=major_rebalance_reasons,
            action_plan=action_plan,
            overall_data_quality=assessment.overall_data_quality,
            data_gaps=data_gaps,
            validation_warnings=validation_warnings,
            references=references,
        )
    except ValidationError as exc:
        raise PortfolioReviewAIError("Portfolio review failed final validation") from exc


def _build_action_plan(
    *,
    rebalance_recommended: models_review.PortfolioReviewRebalanceFlag,
    calculated_actions: _CalculatedActions | None,
    action_plan_draft: _PortfolioActionPlanDraft | None,
) -> models_review.PortfolioReviewActionPlan | None:
    if calculated_actions is None or action_plan_draft is None:
        if calculated_actions is not None or action_plan_draft is not None:
            raise PortfolioReviewAIError("Portfolio review action-plan state is incomplete")
        return None

    candidates = {candidate.action_id: candidate for candidate in calculated_actions.candidates}
    ordered_reasoning = sorted(action_plan_draft.actions, key=lambda action: action.priority)
    actions = [
        models_review.PortfolioReviewAction(
            priority=reasoning.priority,
            action=candidates[reasoning.action_id].action,
            ticker=candidates[reasoning.action_id].ticker,
            company_name=candidates[reasoning.action_id].company_name,
            current_allocation=candidates[reasoning.action_id].current_allocation,
            target_allocation=candidates[reasoning.action_id].target_allocation,
            quantity=candidates[reasoning.action_id].quantity,
            market_price=candidates[reasoning.action_id].market_price,
            estimated_amount=candidates[reasoning.action_id].estimated_amount,
            instruction=candidates[reasoning.action_id].instruction,
            reasoning=reasoning.reasoning,
            reference_ids=candidates[reasoning.action_id].reference_ids,
        )
        for reasoning in ordered_reasoning
    ]
    return models_review.PortfolioReviewActionPlan(
        plan_type="Rebalance" if rebalance_recommended == "YES" else "Growth",
        budget=calculated_actions.budget,
        cash_ledger=calculated_actions.cash_ledger,
        summary=action_plan_draft.summary,
        actions=actions,
    )


def _review_input_json(
    *,
    portfolio_id: str,
    snapshot: models_review.PortfolioReviewSnapshot,
    investor_theme: str,
    strategy: models_review.PortfolioReviewStrategy,
    budget: models_construction.PortfolioBudget,
) -> str:
    return json.dumps(
        {
            "portfolio_id": portfolio_id,
            "investor_theme": investor_theme,
            "strategy": strategy,
            "budget": budget.model_dump(mode="json"),
            "snapshot": snapshot.model_dump(mode="json"),
        },
        sort_keys=True,
    )


def _stage_cache_key(
    namespace: str,
    prompt: str,
    response_model: type[models_ai.StrictAIModel],
    task_id: str,
) -> str:
    return cache.generate_key(
        namespace,
        prompt,
        json.dumps(response_model.model_json_schema(), sort_keys=True),
        _task_cache_identity(task_id),
    )


def _final_cache_key(
    *,
    snapshot: models_review.PortfolioReviewSnapshot,
    investor_theme: str,
    strategy: models_review.PortfolioReviewStrategy,
    rebalance_requested: bool,
    plan: _PortfolioReviewPlan,
    research: _PortfolioResearch,
    assessment: _PortfolioAssessmentDraft,
    target_draft: _PortfolioTargetDraft,
    budget: models_construction.PortfolioBudget,
    verified_addition_quotes: portfolio_verification.VerifiedSecurityQuotes | None,
    calculated_actions: _CalculatedActions | None,
) -> str:
    return cache.generate_key(
        _FINAL_CACHE_NAMESPACE,
        json.dumps(
            {
                "snapshot": snapshot.model_dump(mode="json"),
                "investor_theme": investor_theme,
                "strategy": strategy,
                "rebalance_requested": rebalance_requested,
                "plan": plan.model_dump(mode="json"),
                "research": research.model_dump(mode="json"),
                "assessment": assessment.model_dump(mode="json"),
                "target": target_draft.model_dump(mode="json"),
                "budget": budget.model_dump(mode="json"),
                "verified_addition_quotes": (
                    verified_addition_quotes.model_dump(mode="json") if verified_addition_quotes else None
                ),
                "calculated_actions": (calculated_actions.model_dump(mode="json") if calculated_actions else None),
            },
            sort_keys=True,
        ),
        date.today().isoformat(),
        ai_prompt_utils.load_prompt(_PLAN_PROMPT),
        ai_prompt_utils.load_prompt(_RESEARCH_PROMPT),
        ai_prompt_utils.load_prompt(_ASSESS_PROMPT),
        ai_prompt_utils.load_prompt(_TARGET_PROMPT),
        ai_prompt_utils.load_prompt(_ACTION_PLAN_PROMPT),
        json.dumps(_PortfolioReviewPlan.model_json_schema(), sort_keys=True),
        json.dumps(_PortfolioResearchResponse.model_json_schema(), sort_keys=True),
        json.dumps(_PortfolioAssessmentDraft.model_json_schema(), sort_keys=True),
        json.dumps(_PortfolioTargetDraft.model_json_schema(), sort_keys=True),
        json.dumps(_PortfolioActionPlanDraft.model_json_schema(), sort_keys=True),
        json.dumps(models_review.PortfolioReview.model_json_schema(), sort_keys=True),
        _task_cache_identity(_PLAN_TASK),
        _task_cache_identity(_RESEARCH_TASK),
        _task_cache_identity(_ASSESS_TASK),
        _task_cache_identity(_TARGET_TASK),
        _task_cache_identity(_ACTION_PLAN_TASK),
    )


def _task_cache_identity(task_id: str) -> str:
    task_config = config.settings_llm_task.tasks.get(task_id)
    if task_config is None:
        return task_id
    return json.dumps(
        {
            "task": task_id,
            "config": task_config.model_dump(mode="json"),
        },
        sort_keys=True,
    )


def _cached_plan(value: object) -> _PortfolioReviewPlan:
    try:
        return (
            value.model_copy(deep=True)
            if isinstance(value, _PortfolioReviewPlan)
            else _PortfolioReviewPlan.model_validate(value)
        )
    except (TypeError, ValidationError) as exc:
        raise RuntimeError("Portfolio review planning cache contains an invalid value") from exc


def _cached_research(value: object) -> _PortfolioResearch:
    try:
        return (
            value.model_copy(deep=True)
            if isinstance(value, _PortfolioResearch)
            else _PortfolioResearch.model_validate(value)
        )
    except (TypeError, ValidationError) as exc:
        raise RuntimeError("Portfolio review research cache contains an invalid value") from exc


def _cached_assessment(value: object) -> _PortfolioAssessmentDraft:
    try:
        return (
            value.model_copy(deep=True)
            if isinstance(value, _PortfolioAssessmentDraft)
            else _PortfolioAssessmentDraft.model_validate(value)
        )
    except (TypeError, ValidationError) as exc:
        raise RuntimeError("Portfolio review assessment cache contains an invalid value") from exc


def _cached_target(value: object) -> _PortfolioTargetDraft:
    try:
        return (
            value.model_copy(deep=True)
            if isinstance(value, _PortfolioTargetDraft)
            else _PortfolioTargetDraft.model_validate(value)
        )
    except (TypeError, ValidationError) as exc:
        raise RuntimeError("Portfolio review target cache contains an invalid value") from exc


def _cached_action_plan(value: object) -> _PortfolioActionPlanDraft:
    try:
        return (
            value.model_copy(deep=True)
            if isinstance(value, _PortfolioActionPlanDraft)
            else _PortfolioActionPlanDraft.model_validate(value)
        )
    except (TypeError, ValidationError) as exc:
        raise RuntimeError("Portfolio review action-plan cache contains an invalid value") from exc


def _cached_review(value: object) -> models_review.PortfolioReview:
    try:
        return (
            value.model_copy(deep=True)
            if isinstance(value, models_review.PortfolioReview)
            else models_review.PortfolioReview.model_validate(value)
        )
    except (TypeError, ValidationError) as exc:
        raise RuntimeError("Portfolio review final cache contains an invalid value") from exc
