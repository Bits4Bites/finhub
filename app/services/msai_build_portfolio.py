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
from ..models import portfolio as models_portfolio
from ..models import types as models_types
from ..utils import ai_prompt as ai_prompt_utils
from ..utils import ai_reference as ai_reference_utils
from ..utils import cache, conv
from . import ai_helper, portfolio_verification

_PLAN_TASK = "BUILD_PORTFOLIO_PLAN"
_RESEARCH_TASK = "BUILD_PORTFOLIO_RESEARCH"
_CONSTRUCT_TASK = "BUILD_PORTFOLIO_CONSTRUCT"
_ACTION_PLAN_TASK = "BUILD_PORTFOLIO_ACTION_PLAN"

_PLAN_PROMPT = "portfolio_construction_plan.txt"
_RESEARCH_PROMPT = "portfolio_construction_research.txt"
_CONSTRUCT_PROMPT = "portfolio_construction_construct.txt"
_ACTION_PLAN_PROMPT = "portfolio_construction_action_plan.txt"

_PLAN_SCHEMA_NAME = "portfolio_construction_plan"
_RESEARCH_SCHEMA_NAME = "portfolio_construction_research"
_CONSTRUCT_SCHEMA_NAME = "portfolio_construction_target"
_ACTION_PLAN_SCHEMA_NAME = "portfolio_construction_action_plan"

_PLAN_CACHE_NAMESPACE = "portfolio-construction-plan-v2"
_RESEARCH_CACHE_NAMESPACE = "portfolio-construction-research-v1"
_CONSTRUCT_CACHE_NAMESPACE = "portfolio-construction-draft-v1"
_ACTION_PLAN_CACHE_NAMESPACE = "portfolio-construction-action-plan-v1"
_FINAL_CACHE_NAMESPACE = "portfolio-construction-final-v3"
_AI_STAGE_CACHE_TTL = 60 * 60
_ALLOCATION_TOLERANCE = 0.01
_MONEY_QUANTUM = Decimal("0.000001")
_INFERRED_BUDGET_MIN_RATE = Decimal("0.10")
_INFERRED_BUDGET_MAX_RATE = Decimal("0.15")
_CURRENCY_CODES = "AUD|CAD|CHF|CNY|EUR|GBP|HKD|INR|JPY|NZD|SGD|USD|VND"
_CURRENCY_MARKERS = rf"{_CURRENCY_CODES}|A\$|[$€£¥]"
_AMOUNT_TOKEN = (
    r"(?P<number>(?:\d{1,3}(?:[,\s]\d{3})+|\d+)(?:\.\d+)?)"
    r"(?:\s*(?P<scale>[kKmM])(?![A-Za-z]))?(?![\d,])"
)
_BUDGET_PATTERNS = (
    re.compile(
        rf"(?P<source>(?P<currency>{_CURRENCY_MARKERS})\s*{_AMOUNT_TOKEN})",
        re.IGNORECASE,
    ),
    re.compile(
        rf"(?P<source>{_AMOUNT_TOKEN}\s*(?P<currency>{_CURRENCY_CODES}))",
        re.IGNORECASE,
    ),
    re.compile(
        rf"(?P<source>(?:total\s+|recurring\s+|regular\s+)?"
        rf"(?:portfolio\s+)?(?:budget|investment(?:\s+amount)?|contribution|capital|"
        rf"invest|contribute|deploy|fund|allocate|put\s+in)"
        rf"\s*(?:of|is|:|=)?\s*{_AMOUNT_TOKEN})",
        re.IGNORECASE,
    ),
)
_BUDGET_CONTEXT_PATTERN = re.compile(
    r"\b(?:budget|invest(?:ment)?|contribut(?:e|ion|ions)?|capital|portfolio|deploy|fund|"
    r"lump[\s-]?sum|recurring|weekly|fortnightly|biweekly|monthly|quarterly|annually|yearly)\b",
    re.IGNORECASE,
)
_NEGATIVE_BUDGET_PATTERN = re.compile(
    rf"\b(?:budget|investment|contribution|invest|contribute|deploy|fund)\b"
    rf"[^.;!?\n]{{0,30}}(?:-\s*(?:{_CURRENCY_MARKERS})?\s*\d|"
    rf"(?:{_CURRENCY_MARKERS})\s*-\s*\d)",
    re.IGNORECASE,
)


class PortfolioConstructionAIError(RuntimeError):
    pass


class _PortfolioConstructionPlan(models_ai.StrictAIModel):
    construction_mode: models_construction.PortfolioConstructionMode
    budget: models_construction.PortfolioBudget
    objective: models_types.NonEmptyString = Field(max_length=4000)
    theme_interpretation: models_types.NonEmptyString = Field(max_length=4000)
    constraints: list[Annotated[models_types.NonEmptyString, Field(max_length=1000)]] = Field(
        min_length=1,
        max_length=12,
    )
    selection_criteria: list[Annotated[models_types.NonEmptyString, Field(max_length=1000)]] = Field(
        min_length=3,
        max_length=12,
    )
    diversification_requirements: list[Annotated[models_types.NonEmptyString, Field(max_length=1000)]] = Field(
        min_length=2,
        max_length=10,
    )
    seed_strategy: models_types.NonEmptyString = Field(max_length=4000)
    research_queries: list[Annotated[models_types.NonEmptyString, Field(max_length=1000)]] = Field(
        min_length=3,
        max_length=12,
    )
    target_holding_count: int = Field(ge=3, le=20)
    data_gaps: list[Annotated[models_types.NonEmptyString, Field(max_length=1000)]] = Field(
        max_length=20,
    )


class _PortfolioResearchCandidate(models_ai.StrictAIModel):
    ticker: str = Field(min_length=1, max_length=models_portfolio.MAX_TICKER_LENGTH)
    company_name: str | None = Field(
        max_length=models_portfolio.MAX_COMPANY_NAME_LENGTH,
    )
    role: models_types.NonEmptyString = Field(max_length=1000)
    theme_fit: models_types.NonEmptyString = Field(max_length=4000)
    investment_case: models_types.NonEmptyString = Field(max_length=4000)
    key_risks: list[Annotated[models_types.NonEmptyString, Field(max_length=1000)]] = Field(
        min_length=1,
        max_length=8,
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
    def validate_candidate(self) -> Self:
        if len(self.reference_ids) != len(set(self.reference_ids)):
            raise ValueError("candidate reference_ids must be unique")
        return self


class _PortfolioResearchResponse(models_ai.StrictAIModel):
    candidates: list[_PortfolioResearchCandidate] = Field(min_length=3, max_length=20)
    data_gaps: list[Annotated[models_types.NonEmptyString, Field(max_length=1000)]] = Field(
        max_length=20,
    )
    references: list[models_ai.ReferenceSourceMetadata] = Field(min_length=1, max_length=20)


class _PortfolioResearchDraft(_PortfolioResearchResponse):
    @model_validator(mode="after")
    def validate_research(self) -> Self:
        tickers = [candidate.ticker for candidate in self.candidates]
        if len(tickers) != len(set(tickers)):
            raise ValueError("research candidate tickers must be unique")
        ai_reference_utils.validate_reference_registry(self.references, self)
        return self


class _PortfolioResearch(models_ai.StrictAIModel):
    as_of: datetime
    candidates: list[_PortfolioResearchCandidate] = Field(min_length=3, max_length=20)
    data_gaps: list[Annotated[models_types.NonEmptyString, Field(max_length=1000)]] = Field(
        max_length=20,
    )
    references: list[models_ai.ReferenceSource] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def validate_research(self) -> Self:
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("research as_of must be timezone-aware")
        tickers = [candidate.ticker for candidate in self.candidates]
        if len(tickers) != len(set(tickers)):
            raise ValueError("research candidate tickers must be unique")
        ai_reference_utils.validate_reference_registry(self.references, self)
        return self


class _PortfolioConstructionPositionDraft(models_ai.StrictAIModel):
    ticker: str = Field(min_length=1, max_length=models_portfolio.MAX_TICKER_LENGTH)
    allocation: float = Field(gt=0, le=1, allow_inf_nan=False)
    role: models_types.NonEmptyString = Field(max_length=1000)
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
            raise ValueError("position reference_ids must be unique")
        return self


class _PortfolioConstructionDraft(models_ai.StrictAIModel):
    summary: models_types.NonEmptyString = Field(max_length=4000)
    positions: list[_PortfolioConstructionPositionDraft] = Field(min_length=3, max_length=20)
    overall_data_quality: models_types.DataQuality
    data_gaps: list[Annotated[models_types.NonEmptyString, Field(max_length=1000)]] = Field(
        max_length=20,
    )

    @model_validator(mode="after")
    def validate_construction(self) -> Self:
        tickers = [position.ticker for position in self.positions]
        if len(tickers) != len(set(tickers)):
            raise ValueError("constructed portfolio tickers must be unique")
        allocation_total = sum(position.allocation for position in self.positions)
        if abs(allocation_total - 1.0) > _ALLOCATION_TOLERANCE:
            raise ValueError("constructed portfolio allocations must sum to one")
        return self


class _PortfolioActionReasoning(models_ai.StrictAIModel):
    action_id: str = Field(min_length=1, max_length=128)
    priority: int = Field(ge=1, le=70)
    reasoning: models_types.NonEmptyString = Field(max_length=4000)


class _PortfolioActionPlanDraft(models_ai.StrictAIModel):
    summary: models_types.NonEmptyString = Field(max_length=4000)
    steps: list[_PortfolioActionReasoning] = Field(min_length=1, max_length=70)

    @model_validator(mode="after")
    def validate_action_plan(self) -> Self:
        action_ids = [step.action_id for step in self.steps]
        if len(action_ids) != len(set(action_ids)):
            raise ValueError("action-plan action IDs must be unique")
        priorities = sorted(step.priority for step in self.steps)
        if priorities != list(range(1, len(self.steps) + 1)):
            raise ValueError("action-plan priorities must be consecutive and start at one")
        return self


class _PortfolioActionCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_id: str
    action: models_construction.PortfolioActionType
    ticker: str
    company_name: str | None
    instruction: str
    quantity: int | None = Field(ge=1)
    market_price: float | None = Field(gt=0, allow_inf_nan=False)
    estimated_amount: float | None = Field(ge=0, allow_inf_nan=False)
    target_allocation: float | None = Field(gt=0, le=1, allow_inf_nan=False)
    reference_ids: list[str]
    priority_group: Literal[0, 1, 2, 3, 4]
    priority_score: float


class _CalculatedActions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    budget_utilized: float | None = Field(ge=0, allow_inf_nan=False)
    unallocated_amount: float | None = Field(ge=0, allow_inf_nan=False)
    candidates: list[_PortfolioActionCandidate] = Field(min_length=1, max_length=70)
    data_gaps: list[str] = Field(max_length=20)


def _extract_budget(
    investor_theme: str,
    *,
    default_currency: str,
) -> models_construction.PortfolioBudget:
    if _NEGATIVE_BUDGET_PATTERN.search(investor_theme):
        raise portfolio_verification.PortfolioInputError("Investment budget must be a positive finite amount")
    matches: list[tuple[int, int, Decimal, str, str, bool]] = []
    for pattern in _BUDGET_PATTERNS:
        for match in pattern.finditer(investor_theme):
            start, end = match.span("source")
            context = investor_theme[max(0, start - 60) : min(len(investor_theme), end + 60)]
            currency_marker = match.groupdict().get("currency")
            if not currency_marker and not _BUDGET_CONTEXT_PATTERN.search(context):
                continue
            if not currency_marker and re.match(
                r"\s*(?:%|percent|ETFs?|stocks?|holdings?|positions?|years?)\b",
                investor_theme[end:],
                re.IGNORECASE,
            ):
                continue
            immediate_context = investor_theme[max(0, start - 40) : min(len(investor_theme), end + 40)]
            if re.search(
                r"\b(?:salary|income|revenue|price|priced|pricing|per\s+share|"
                r"share\s+price|stocks?\s+(?:under|below|above)|market\s+cap|"
                r"dividend|fee|expense|debt)\b",
                immediate_context,
                re.IGNORECASE,
            ) and not re.search(
                r"\b(?:budget|contribut(?:e|ion|ions)?|deploy|fund|lump[\s-]?sum)\b",
                immediate_context,
                re.IGNORECASE,
            ):
                continue

            number_text = match.group("number").replace(",", "").replace(" ", "")
            amount = Decimal(number_text)
            scale = (match.group("scale") or "").lower()
            if scale == "k":
                amount *= Decimal("1000")
            elif scale == "m":
                amount *= Decimal("1000000")
            if not amount.is_finite() or amount <= 0:
                raise portfolio_verification.PortfolioInputError("Investment budget must be a positive finite amount")

            currency = _resolve_budget_currency(
                currency_marker,
                default_currency=default_currency,
            )
            source_text = _budget_source_excerpt(investor_theme, start=start, end=end)
            matches.append(
                (
                    start,
                    end,
                    amount,
                    currency,
                    source_text,
                    bool(currency_marker),
                )
            )

    matches.sort(key=lambda item: (-item[5], -(item[1] - item[0]), item[0]))
    non_overlapping: list[tuple[int, int, Decimal, str, str, bool]] = []
    for candidate in matches:
        if any(candidate[0] < existing[1] and candidate[1] > existing[0] for existing in non_overlapping):
            continue
        non_overlapping.append(candidate)
    non_overlapping.sort(key=lambda item: item[0])

    if not non_overlapping:
        return models_construction.PortfolioBudget(
            budget_type="NotProvided",
            is_inferred=False,
            amount=None,
            currency=None,
            frequency=None,
            source_text=None,
        )
    distinct_budgets = {(amount, currency) for _, _, amount, currency, _, _ in non_overlapping}
    if len(distinct_budgets) != 1:
        raise portfolio_verification.PortfolioInputError(
            "Investor theme contains multiple investment amounts; provide one total or recurring budget"
        )

    start, end, amount, currency, source_text, _ = non_overlapping[0]
    context = investor_theme[max(0, start - 60) : min(len(investor_theme), end + 60)]
    frequency_context = investor_theme[max(0, start - 45) : min(len(investor_theme), end + 45)]
    frequency = _budget_frequency(frequency_context)
    recurring_mentioned = re.search(
        r"\b(?:recurring|regular|contribut(?:e|ion|ions)|each)\b",
        context,
        re.IGNORECASE,
    )
    total_mentioned = re.search(
        r"\b(?:total|lump[\s-]?sum|one[\s-]?off)\b",
        context,
        re.IGNORECASE,
    )
    if total_mentioned and not recurring_mentioned:
        frequency = None
    if recurring_mentioned and frequency is None:
        raise portfolio_verification.PortfolioInputError(
            "Recurring investment budget must include a weekly, fortnightly, monthly, quarterly, or annual frequency"
        )

    try:
        return models_construction.PortfolioBudget(
            budget_type=("Recurring" if frequency is not None else "Total"),
            is_inferred=False,
            amount=float(amount),
            currency=currency,
            frequency=frequency,
            source_text=source_text,
        )
    except ValidationError as exc:
        raise portfolio_verification.PortfolioInputError(
            "Investment budget contains an unsupported amount or currency"
        ) from exc


def _budget_source_excerpt(
    investor_theme: str,
    *,
    start: int,
    end: int,
) -> str:
    left = max(investor_theme.rfind(delimiter, 0, start) for delimiter in (".", ";", "!", "?", "\n"))
    right_candidates = [
        position for delimiter in (".", ";", "!", "?", "\n") if (position := investor_theme.find(delimiter, end)) >= 0
    ]
    right = min(right_candidates) if right_candidates else len(investor_theme)
    excerpt = investor_theme[left + 1 : right].strip()
    if len(excerpt) <= 500:
        return excerpt

    local_start = max(left + 1, start - 240)
    local_end = min(right, end + 240)
    return investor_theme[local_start:local_end].strip()


def _resolve_budget_currency(marker: str | None, *, default_currency: str) -> str:
    normalized_marker = marker.strip().upper() if marker else ""
    if not normalized_marker:
        if not default_currency:
            raise portfolio_verification.PortfolioInputError(
                "Investment budget currency could not be inferred from the selected country"
            )
        return default_currency
    if len(normalized_marker) == 3 and normalized_marker.isalpha():
        return normalized_marker
    if normalized_marker == "€":
        return "EUR"
    if normalized_marker == "£":
        return "GBP"
    if normalized_marker == "¥":
        return default_currency if default_currency in {"CNY", "JPY"} else "JPY"
    if normalized_marker == "A$":
        return "AUD"
    if normalized_marker == "$":
        return default_currency if default_currency in {"AUD", "CAD", "HKD", "NZD", "SGD", "USD"} else "USD"
    raise portfolio_verification.PortfolioInputError(f"Unsupported investment budget currency marker: {marker}")


def _budget_frequency(
    context: str,
) -> models_construction.PortfolioBudgetFrequency | None:
    frequency_patterns: tuple[
        tuple[models_construction.PortfolioBudgetFrequency, str],
        ...,
    ] = (
        ("Fortnightly", r"\b(?:fortnightly|biweekly|every\s+two\s+weeks?)\b"),
        ("Weekly", r"\b(?:weekly|per\s+week|each\s+week|every\s+week|a\s+week|/\s*(?:week|wk))\b"),
        ("Monthly", r"\b(?:monthly|per\s+month|each\s+month|every\s+month|a\s+month|/\s*(?:month|mo))\b"),
        (
            "Quarterly",
            r"\b(?:quarterly|per\s+quarter|each\s+quarter|every\s+quarter|a\s+quarter|/\s*(?:quarter|qtr))\b",
        ),
        (
            "Annually",
            r"\b(?:annually|annual|yearly|per\s+year|each\s+year|every\s+year|a\s+year|/\s*(?:year|yr))\b",
        ),
    )
    for frequency, pattern in frequency_patterns:
        if re.search(pattern, context, re.IGNORECASE):
            return frequency
    return None


def _inferred_recurring_budget(
    verified_portfolio: portfolio_verification.VerifiedPortfolio,
    *,
    rate: Decimal,
) -> models_construction.PortfolioBudget:
    amount = (Decimal(str(verified_portfolio.total_market_value)) * rate).quantize(_MONEY_QUANTUM)
    if amount <= 0:
        raise PortfolioConstructionAIError("Verified holdings are too small to infer an investment budget")
    return models_construction.PortfolioBudget(
        budget_type="Recurring",
        is_inferred=True,
        amount=float(amount),
        currency=verified_portfolio.currency,
        frequency=None,
        source_text=(
            f"Application-inferred next-iteration contribution at {rate:.0%} of verified current holdings market value."
        ),
    )


async def ai_build_portfolio(
    portfolio: list[models_portfolio.PortfolioHolding],
    *,
    country: str,
    investor_theme: str,
) -> models_construction.PortfolioConstruction:
    normalized_country = conv.country_to_iso2(country.strip())
    if not normalized_country:
        raise portfolio_verification.PortfolioInputError("Unsupported or unknown country")

    normalized_theme = investor_theme.strip()
    if not normalized_theme:
        raise portfolio_verification.PortfolioInputError("Investor theme must not be empty")

    active_positions = [position for position in portfolio if position.num_shares > 0]
    if any(not float(position.num_shares).is_integer() for position in active_positions):
        raise portfolio_verification.PortfolioInputError("Portfolio construction supports whole-share holdings only")
    construction_mode: models_construction.PortfolioConstructionMode = "Seeded" if active_positions else "Scratch"
    verified_portfolio = (
        await portfolio_verification.verify_portfolio(
            active_positions,
            country=normalized_country,
        )
        if active_positions
        else None
    )
    portfolio_currency = (
        verified_portfolio.currency if verified_portfolio else conv.country_to_currency_code(normalized_country)
    )
    budget = _extract_budget(
        normalized_theme,
        default_currency=portfolio_currency,
    )
    if budget.budget_type == "NotProvided" and verified_portfolio is not None:
        budget = _inferred_recurring_budget(
            verified_portfolio,
            rate=_INFERRED_BUDGET_MIN_RATE,
        )
    if budget.currency is not None and portfolio_currency and budget.currency != portfolio_currency:
        raise portfolio_verification.PortfolioInputError(
            f"Investment budget currency must match the {portfolio_currency} portfolio currency"
        )

    plan = await _plan_portfolio(
        country=normalized_country,
        investor_theme=normalized_theme,
        construction_mode=construction_mode,
        verified_portfolio=verified_portfolio,
        budget=budget,
    )
    research = await _research_portfolio(
        country=normalized_country,
        investor_theme=normalized_theme,
        construction_mode=construction_mode,
        verified_portfolio=verified_portfolio,
        plan=plan,
    )
    draft = await _construct_portfolio(
        country=normalized_country,
        investor_theme=normalized_theme,
        construction_mode=construction_mode,
        verified_portfolio=verified_portfolio,
        plan=plan,
        research=research,
    )
    target_positions = _build_target_positions(draft, research)
    verified_quotes = None
    if budget.budget_type != "NotProvided":
        try:
            verified_quotes = await portfolio_verification.verify_security_quotes(
                [position.ticker for position in target_positions],
                country=normalized_country,
            )
            _validate_target_quotes(
                target_positions,
                verified_quotes,
                budget=budget,
                verified_portfolio=verified_portfolio,
            )
        except (
            portfolio_verification.PortfolioInputError,
            portfolio_verification.PortfolioVerificationError,
            ValueError,
        ) as exc:
            raise PortfolioConstructionAIError("Portfolio construction target-price verification failed") from exc

    calculated_actions = None
    if budget.budget_type != "NotProvided":
        budget, calculated_actions = _resolve_action_budget(
            target_positions=target_positions,
            verified_portfolio=verified_portfolio,
            verified_quotes=verified_quotes,
            budget=budget,
        )
        if plan.budget != budget:
            plan = plan.model_copy(update={"budget": budget})

    final_cache_key = _final_cache_key(
        country=normalized_country,
        investor_theme=normalized_theme,
        construction_mode=construction_mode,
        verified_portfolio=verified_portfolio,
        budget=budget,
        plan=plan,
        research=research,
        draft=draft,
        verified_quotes=verified_quotes,
    )
    cached_construction = await cache.get(final_cache_key)
    if cached_construction is not None:
        return _cached_final(cached_construction)

    action_plan_draft = (
        await _create_action_plan(
            country=normalized_country,
            investor_theme=normalized_theme,
            construction_mode=construction_mode,
            verified_portfolio=verified_portfolio,
            plan=plan,
            research=research,
            target_positions=target_positions,
            calculated_actions=calculated_actions,
        )
        if calculated_actions is not None
        else None
    )
    construction = _finalize_portfolio(
        country=normalized_country,
        investor_theme=normalized_theme,
        construction_mode=construction_mode,
        verified_portfolio=verified_portfolio,
        plan=plan,
        research=research,
        draft=draft,
        target_positions=target_positions,
        calculated_actions=calculated_actions,
        action_plan_draft=action_plan_draft,
    )
    await cache.set(
        final_cache_key,
        construction.model_dump(mode="json"),
        ttl=_AI_STAGE_CACHE_TTL,
    )
    return construction


async def _plan_portfolio(
    *,
    country: str,
    investor_theme: str,
    construction_mode: models_construction.PortfolioConstructionMode,
    verified_portfolio: portfolio_verification.VerifiedPortfolio | None,
    budget: models_construction.PortfolioBudget,
) -> _PortfolioConstructionPlan:
    prompt = ai_prompt_utils.render_prompt(
        _PLAN_PROMPT,
        {
            "CONSTRUCTION_INPUT_JSON": _construction_input_json(
                country=country,
                investor_theme=investor_theme,
                construction_mode=construction_mode,
                verified_portfolio=verified_portfolio,
                budget=budget,
            ),
            "MARKET_DATE": date.today().isoformat(),
        },
    )
    cache_key = _stage_cache_key(
        _PLAN_CACHE_NAMESPACE,
        prompt,
        _PortfolioConstructionPlan,
        _PLAN_TASK,
    )
    cached_plan = await cache.get(cache_key)
    if cached_plan is not None:
        return _cached_plan(cached_plan)

    response = await _execute_stage(
        _PLAN_TASK,
        prompt,
        country=country,
        response_model=_PortfolioConstructionPlan,
        schema_name=_PLAN_SCHEMA_NAME,
        stage_name="planning",
    )
    try:
        plan = _PortfolioConstructionPlan.model_validate_json(response.completion)
        if plan.construction_mode != construction_mode:
            raise ValueError("plan returned a different construction mode")
        if plan.budget != budget:
            raise ValueError("plan changed the deterministically extracted investment budget")
    except (ValueError, ValidationError) as exc:
        raise PortfolioConstructionAIError("Portfolio construction planning returned invalid structured data") from exc

    await cache.set(cache_key, plan.model_dump(mode="json"), ttl=_AI_STAGE_CACHE_TTL)
    return plan


async def _research_portfolio(
    *,
    country: str,
    investor_theme: str,
    construction_mode: models_construction.PortfolioConstructionMode,
    verified_portfolio: portfolio_verification.VerifiedPortfolio | None,
    plan: _PortfolioConstructionPlan,
) -> _PortfolioResearch:
    prompt = ai_prompt_utils.render_prompt(
        _RESEARCH_PROMPT,
        {
            "CONSTRUCTION_INPUT_JSON": _construction_input_json(
                country=country,
                investor_theme=investor_theme,
                construction_mode=construction_mode,
                verified_portfolio=verified_portfolio,
                budget=plan.budget,
            ),
            "PLAN_JSON": plan.model_dump_json(),
            "MARKET_DATE": date.today().isoformat(),
        },
    )
    cache_key = _stage_cache_key(
        _RESEARCH_CACHE_NAMESPACE,
        prompt,
        _PortfolioResearchDraft,
        _RESEARCH_TASK,
    )
    cached_research = await cache.get(cache_key)
    if cached_research is not None:
        return _cached_research(cached_research)

    response = await _execute_stage(
        _RESEARCH_TASK,
        prompt,
        country=country,
        response_model=_PortfolioResearchResponse,
        schema_name=_RESEARCH_SCHEMA_NAME,
        stage_name="research",
    )
    try:
        research_response = _PortfolioResearchResponse.model_validate_json(response.completion)
        repaired_research = _repair_research_references(research_response)
        if len(repaired_research.candidates) > min(
            20,
            plan.target_holding_count + 5,
        ):
            raise ValueError("research returned too many candidates for the plan")
        research = _finalize_research_references(
            repaired_research,
            response.citation_urls,
            accessed_at=datetime.now(UTC),
        )
    except (TypeError, ValueError, ValidationError) as exc:
        raise PortfolioConstructionAIError("Portfolio construction research returned invalid structured data") from exc

    await cache.set(cache_key, research.model_dump(mode="json"), ttl=_AI_STAGE_CACHE_TTL)
    return research


async def _construct_portfolio(
    *,
    country: str,
    investor_theme: str,
    construction_mode: models_construction.PortfolioConstructionMode,
    verified_portfolio: portfolio_verification.VerifiedPortfolio | None,
    plan: _PortfolioConstructionPlan,
    research: _PortfolioResearch,
) -> _PortfolioConstructionDraft:
    prompt = ai_prompt_utils.render_prompt(
        _CONSTRUCT_PROMPT,
        {
            "CONSTRUCTION_INPUT_JSON": _construction_input_json(
                country=country,
                investor_theme=investor_theme,
                construction_mode=construction_mode,
                verified_portfolio=verified_portfolio,
                budget=plan.budget,
            ),
            "PLAN_JSON": plan.model_dump_json(),
            "RESEARCH_JSON": research.model_dump_json(),
        },
    )
    cache_key = _stage_cache_key(
        _CONSTRUCT_CACHE_NAMESPACE,
        prompt,
        _PortfolioConstructionDraft,
        _CONSTRUCT_TASK,
    )
    cached_draft = await cache.get(cache_key)
    if cached_draft is not None:
        return _cached_draft(cached_draft)

    response = await _execute_stage(
        _CONSTRUCT_TASK,
        prompt,
        country=country,
        response_model=_PortfolioConstructionDraft,
        schema_name=_CONSTRUCT_SCHEMA_NAME,
        stage_name="construction",
    )
    try:
        draft = _PortfolioConstructionDraft.model_validate_json(response.completion)
        if len(draft.positions) > plan.target_holding_count:
            raise ValueError("constructed portfolio exceeds the planned holding count")
        _validate_draft_against_research(draft, research)
    except (ValueError, ValidationError) as exc:
        raise PortfolioConstructionAIError("Portfolio construction returned invalid structured data") from exc

    await cache.set(cache_key, draft.model_dump(mode="json"), ttl=_AI_STAGE_CACHE_TTL)
    return draft


async def _create_action_plan(
    *,
    country: str,
    investor_theme: str,
    construction_mode: models_construction.PortfolioConstructionMode,
    verified_portfolio: portfolio_verification.VerifiedPortfolio | None,
    plan: _PortfolioConstructionPlan,
    research: _PortfolioResearch,
    target_positions: list[models_construction.PortfolioTargetPosition],
    calculated_actions: _CalculatedActions,
) -> _PortfolioActionPlanDraft:
    prompt_candidates = [
        candidate.model_dump(
            mode="json",
            exclude={"priority_group", "priority_score"},
        )
        for candidate in calculated_actions.candidates
    ]
    prompt = ai_prompt_utils.render_prompt(
        _ACTION_PLAN_PROMPT,
        {
            "CONSTRUCTION_INPUT_JSON": _construction_input_json(
                country=country,
                investor_theme=investor_theme,
                construction_mode=construction_mode,
                verified_portfolio=verified_portfolio,
                budget=plan.budget,
            ),
            "PLAN_JSON": plan.model_dump_json(),
            "RESEARCH_JSON": research.model_dump_json(),
            "TARGET_PORTFOLIO_JSON": json.dumps(
                [position.model_dump(mode="json") for position in target_positions],
                sort_keys=True,
            ),
            "ACTION_CANDIDATES_JSON": json.dumps(
                {
                    "budget_utilized": calculated_actions.budget_utilized,
                    "unallocated_amount": calculated_actions.unallocated_amount,
                    "actions": prompt_candidates,
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
            raise RuntimeError("Portfolio construction action-plan cache contains an invalid value") from exc
        return draft

    response = await _execute_stage(
        _ACTION_PLAN_TASK,
        prompt,
        country=country,
        response_model=_PortfolioActionPlanDraft,
        schema_name=_ACTION_PLAN_SCHEMA_NAME,
        stage_name="action planning",
    )
    try:
        draft = _PortfolioActionPlanDraft.model_validate_json(response.completion)
        _validate_action_plan_draft(draft, calculated_actions.candidates)
    except (ValueError, ValidationError) as exc:
        raise PortfolioConstructionAIError(
            "Portfolio construction action planning returned invalid structured data"
        ) from exc

    await cache.set(cache_key, draft.model_dump(mode="json"), ttl=_AI_STAGE_CACHE_TTL)
    return draft


def _validate_action_plan_draft(
    draft: _PortfolioActionPlanDraft,
    candidates: list[_PortfolioActionCandidate],
) -> None:
    candidate_ids = {candidate.action_id for candidate in candidates}
    response_ids = {step.action_id for step in draft.steps}
    if response_ids != candidate_ids or len(draft.steps) != len(candidate_ids):
        raise ValueError("action plan did not preserve the calculated action set")
    candidate_by_id = {candidate.action_id: candidate for candidate in candidates}
    ordered_groups = [
        candidate_by_id[step.action_id].priority_group for step in sorted(draft.steps, key=lambda item: item.priority)
    ]
    if ordered_groups != sorted(ordered_groups):
        raise ValueError("action plan violated fixed action-category priority")


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
        logging.exception("[Portfolio Construction] %s provider call failed.", stage_name.capitalize())
        raise PortfolioConstructionAIError(f"Portfolio construction {stage_name} provider failed") from exc
    if response.is_error:
        logging.error(
            "[Portfolio Construction] %s failed: %s",
            stage_name.capitalize(),
            response.error_msg,
        )
        raise PortfolioConstructionAIError(f"Portfolio construction {stage_name} failed")
    return response


def _repair_research_references(
    research: _PortfolioResearchResponse,
) -> _PortfolioResearchDraft:
    research_data = research.model_dump()
    registry_ids = {reference.id for reference in research.references}
    missing_ids: set[str] = set()
    repaired_candidates = []
    dropped_candidates = 0

    for candidate in research_data["candidates"]:
        unknown_ids = set(candidate["reference_ids"]) - registry_ids
        missing_ids.update(unknown_ids)
        valid_ids = [reference_id for reference_id in candidate["reference_ids"] if reference_id in registry_ids]
        if not valid_ids:
            dropped_candidates += 1
            continue
        candidate["ticker"] = candidate["ticker"].strip().upper()
        candidate["reference_ids"] = list(dict.fromkeys(valid_ids))
        repaired_candidates.append(candidate)

    research_data["candidates"] = repaired_candidates
    used_ids = ai_reference_utils.collect_reference_ids(research_data)
    research_data["references"] = [
        reference for reference in research_data["references"] if reference["id"] in used_ids
    ]
    if missing_ids or dropped_candidates:
        missing_text = ", ".join(sorted(missing_ids)) or "none"
        warning = f"Ignored missing source IDs: {missing_text}."
        if dropped_candidates:
            warning += f" Removed {dropped_candidates} unsupported candidate(s)."
        research_data["data_gaps"] = [*research_data["data_gaps"][:19], warning]
        logging.warning("[Portfolio Construction] %s", warning)
    return _PortfolioResearchDraft.model_validate(research_data)


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
        raise TypeError("Remapped portfolio research must be an object")
    research_data["as_of"] = accessed_at
    research_data["references"] = [reference.model_dump(mode="python") for reference in canonicalized.references]
    return _PortfolioResearch.model_validate(research_data)


def _validate_draft_against_research(
    draft: _PortfolioConstructionDraft,
    research: _PortfolioResearch,
) -> None:
    candidates = {candidate.ticker: candidate for candidate in research.candidates}
    unknown_tickers = {position.ticker for position in draft.positions if position.ticker not in candidates}
    if unknown_tickers:
        raise ValueError(f"constructed portfolio contains unresearched tickers: {sorted(unknown_tickers)}")

    for position in draft.positions:
        candidate_reference_ids = set(candidates[position.ticker].reference_ids)
        unknown_ids = set(position.reference_ids) - candidate_reference_ids
        if unknown_ids:
            raise ValueError(f"position {position.ticker} contains unsupported reference IDs: {sorted(unknown_ids)}")


def _build_target_positions(
    draft: _PortfolioConstructionDraft,
    research: _PortfolioResearch,
) -> list[models_construction.PortfolioTargetPosition]:
    _validate_draft_against_research(draft, research)
    candidates = {candidate.ticker: candidate for candidate in research.candidates}
    allocation_total = sum(position.allocation for position in draft.positions)
    return [
        models_construction.PortfolioTargetPosition(
            ticker=position.ticker,
            company_name=candidates[position.ticker].company_name,
            allocation=position.allocation / allocation_total,
            role=position.role,
            rationale=position.rationale,
            reference_ids=position.reference_ids,
        )
        for position in draft.positions
    ]


def _validate_target_quotes(
    target_positions: list[models_construction.PortfolioTargetPosition],
    verified_quotes: portfolio_verification.VerifiedSecurityQuotes,
    *,
    budget: models_construction.PortfolioBudget,
    verified_portfolio: portfolio_verification.VerifiedPortfolio | None,
) -> None:
    target_tickers = {position.ticker for position in target_positions}
    quote_tickers = {security.ticker for security in verified_quotes.securities}
    if target_tickers != quote_tickers:
        raise ValueError("verified target quotes do not match the constructed portfolio")
    if budget.currency != verified_quotes.currency:
        raise ValueError(f"target securities use {verified_quotes.currency}, not the {budget.currency} budget currency")
    if verified_portfolio and verified_portfolio.currency != verified_quotes.currency:
        raise ValueError("constructed target securities do not use the verified seed portfolio currency")


def _calculate_actions(
    *,
    target_positions: list[models_construction.PortfolioTargetPosition],
    verified_portfolio: portfolio_verification.VerifiedPortfolio | None,
    verified_quotes: portfolio_verification.VerifiedSecurityQuotes | None,
    budget: models_construction.PortfolioBudget,
) -> _CalculatedActions:
    if budget.budget_type == "NotProvided":
        raise PortfolioConstructionAIError("Portfolio action planning requires a supplied or inferred budget")
    if verified_quotes is None or budget.amount is None or budget.currency is None:
        raise PortfolioConstructionAIError("Portfolio construction lacks verified prices for budget-aware sizing")

    quote_by_ticker = {security.ticker: security for security in verified_quotes.securities}
    prices = {ticker: Decimal(str(security.market_price)) for ticker, security in quote_by_ticker.items()}
    budget_amount = Decimal(str(budget.amount))
    current_values = _target_current_values(
        target_positions,
        verified_portfolio=verified_portfolio,
        prices=prices,
    )
    target_value = sum(current_values.values(), Decimal("0")) + budget_amount
    gaps = {
        position.ticker: max(
            target_value * Decimal(str(position.allocation)) - current_values[position.ticker],
            Decimal("0"),
        )
        for position in target_positions
    }
    gap_total = sum(gaps.values(), Decimal("0"))
    desired_amounts = {
        position.ticker: (
            budget_amount * gaps[position.ticker] / gap_total
            if gap_total > 0
            else budget_amount * Decimal(str(position.allocation))
        )
        for position in target_positions
    }

    quantities, utilized = _allocate_whole_shares(
        budget_amount,
        desired_amounts=desired_amounts,
        prices=prices,
    )
    candidates = _seed_exit_candidates(
        target_positions=target_positions,
        verified_portfolio=verified_portfolio,
    )
    current_holdings = (
        {holding.ticker: holding for holding in verified_portfolio.holdings} if verified_portfolio else {}
    )

    for position in target_positions:
        quote = quote_by_ticker[position.ticker]
        current_holding = current_holdings.get(position.ticker)
        current_quantity = int(current_holding.num_shares) if current_holding else 0
        calculated_quantity = quantities[position.ticker]

        if calculated_quantity > 0:
            candidates.append(
                _action_candidate(
                    action="BUY",
                    position=position,
                    company_name=quote.company_name or position.company_name,
                    instruction=f"BUY {calculated_quantity} whole shares of {position.ticker}.",
                    quantity=calculated_quantity,
                    market_price=quote.market_price,
                    estimated_amount=_round_money(Decimal(calculated_quantity) * prices[position.ticker]),
                    priority_score=float(Decimal(calculated_quantity) * prices[position.ticker]),
                )
            )
        elif current_quantity > 0:
            candidates.append(
                _hold_candidate(
                    position,
                    company_name=quote.company_name or position.company_name,
                    market_price=quote.market_price,
                    instruction=(
                        f"HOLD {current_quantity} whole shares of {position.ticker}; "
                        "apply the new-money budget to underweight targets instead of trimming."
                    ),
                )
            )
        else:
            candidates.append(_accumulate_candidate(position, quote, currency=budget.currency))

    ordered_candidates = _order_action_candidates(candidates)
    budget_utilized = _round_money(utilized)
    unallocated_amount = _round_money(max(budget_amount - utilized, Decimal("0")))
    data_gaps = [budget.source_text] if budget.is_inferred and budget.source_text is not None else []
    unfunded_count = sum(candidate.action == "ACCUMULATE" for candidate in ordered_candidates)
    if unfunded_count:
        data_gaps.append(f"Whole-share pricing left {unfunded_count} target position(s) without a purchasable share.")
    return _CalculatedActions(
        budget_utilized=budget_utilized,
        unallocated_amount=unallocated_amount,
        candidates=ordered_candidates,
        data_gaps=data_gaps,
    )


def _resolve_action_budget(
    *,
    target_positions: list[models_construction.PortfolioTargetPosition],
    verified_portfolio: portfolio_verification.VerifiedPortfolio | None,
    verified_quotes: portfolio_verification.VerifiedSecurityQuotes | None,
    budget: models_construction.PortfolioBudget,
) -> tuple[models_construction.PortfolioBudget, _CalculatedActions]:
    actions = _calculate_actions(
        target_positions=target_positions,
        verified_portfolio=verified_portfolio,
        verified_quotes=verified_quotes,
        budget=budget,
    )
    if not budget.is_inferred or any(candidate.action == "BUY" for candidate in actions.candidates):
        return budget, actions
    if verified_portfolio is None:
        raise PortfolioConstructionAIError("Inferred investment budget requires verified current holdings")

    maximum_budget = _inferred_recurring_budget(
        verified_portfolio,
        rate=_INFERRED_BUDGET_MAX_RATE,
    )
    maximum_actions = _calculate_actions(
        target_positions=target_positions,
        verified_portfolio=verified_portfolio,
        verified_quotes=verified_quotes,
        budget=maximum_budget,
    )
    if any(candidate.action == "BUY" for candidate in maximum_actions.candidates):
        return maximum_budget, maximum_actions
    return budget, actions


def _target_current_values(
    target_positions: list[models_construction.PortfolioTargetPosition],
    *,
    verified_portfolio: portfolio_verification.VerifiedPortfolio | None,
    prices: dict[str, Decimal],
) -> dict[str, Decimal]:
    current_quantities = (
        {holding.ticker: Decimal(str(holding.num_shares)) for holding in verified_portfolio.holdings}
        if verified_portfolio
        else {}
    )
    return {
        position.ticker: current_quantities.get(position.ticker, Decimal("0")) * prices[position.ticker]
        for position in target_positions
    }


def _allocate_whole_shares(
    budget: Decimal,
    *,
    desired_amounts: dict[str, Decimal],
    prices: dict[str, Decimal],
) -> tuple[dict[str, int], Decimal]:
    quantities = {
        ticker: int((desired_amounts[ticker] / prices[ticker]).to_integral_value(rounding=ROUND_FLOOR))
        for ticker in desired_amounts
    }
    utilized = sum(
        (Decimal(quantities[ticker]) * prices[ticker] for ticker in quantities),
        Decimal("0"),
    )
    remaining = budget - utilized

    while True:
        improvements = []
        for ticker, price in prices.items():
            if price > remaining:
                continue
            allocated = Decimal(quantities[ticker]) * price
            improvement = abs(desired_amounts[ticker] - allocated) - abs(desired_amounts[ticker] - allocated - price)
            if improvement > 0:
                improvements.append((improvement, desired_amounts[ticker], ticker))
        if not improvements:
            break
        _, _, selected_ticker = max(improvements, key=lambda item: (item[0], item[1], item[2]))
        quantities[selected_ticker] += 1
        utilized += prices[selected_ticker]
        remaining -= prices[selected_ticker]

    if utilized > budget:
        raise PortfolioConstructionAIError("Whole-share allocation exceeded the investment budget")
    return quantities, utilized


def _seed_exit_candidates(
    *,
    target_positions: list[models_construction.PortfolioTargetPosition],
    verified_portfolio: portfolio_verification.VerifiedPortfolio | None,
) -> list[_PortfolioActionCandidate]:
    if verified_portfolio is None:
        return []
    target_tickers = {position.ticker for position in target_positions}
    return [
        _PortfolioActionCandidate(
            action_id=f"exit:{holding.ticker}",
            action="EXIT",
            ticker=holding.ticker,
            company_name=holding.company_name,
            instruction=f"SELL ALL {int(holding.num_shares)} whole shares of {holding.ticker}.",
            quantity=None,
            market_price=holding.market_price,
            estimated_amount=_round_money(Decimal(str(holding.market_value))),
            target_allocation=None,
            reference_ids=[],
            priority_group=0,
            priority_score=holding.market_value,
        )
        for holding in verified_portfolio.holdings
        if holding.ticker not in target_tickers
    ]


def _action_candidate(
    *,
    action: Literal["TRIM", "BUY", "ACCUMULATE"],
    position: models_construction.PortfolioTargetPosition,
    company_name: str | None,
    instruction: str,
    quantity: int | None,
    market_price: float | None,
    estimated_amount: float | None,
    priority_score: float,
) -> _PortfolioActionCandidate:
    priority_group: Literal[1, 2, 3] = {
        "TRIM": 1,
        "BUY": 2,
        "ACCUMULATE": 3,
    }[action]
    return _PortfolioActionCandidate(
        action_id=f"{action.lower()}:{position.ticker}",
        action=action,
        ticker=position.ticker,
        company_name=company_name,
        instruction=instruction,
        quantity=quantity,
        market_price=market_price,
        estimated_amount=estimated_amount,
        target_allocation=position.allocation,
        reference_ids=position.reference_ids,
        priority_group=priority_group,
        priority_score=priority_score,
    )


def _accumulate_candidate(
    position: models_construction.PortfolioTargetPosition,
    quote: portfolio_verification.VerifiedSecurityQuote,
    *,
    currency: str,
) -> _PortfolioActionCandidate:
    return _action_candidate(
        action="ACCUMULATE",
        position=position,
        company_name=quote.company_name or position.company_name,
        instruction=(
            f"ACCUMULATE cash for {position.ticker}; one whole share currently costs "
            f"about {currency} {quote.market_price:.2f}."
        ),
        quantity=None,
        market_price=quote.market_price,
        estimated_amount=None,
        priority_score=position.allocation,
    )


def _hold_candidate(
    position: models_construction.PortfolioTargetPosition,
    *,
    company_name: str | None,
    market_price: float | None,
    instruction: str,
) -> _PortfolioActionCandidate:
    return _PortfolioActionCandidate(
        action_id=f"hold:{position.ticker}",
        action="HOLD",
        ticker=position.ticker,
        company_name=company_name,
        instruction=instruction,
        quantity=None,
        market_price=market_price,
        estimated_amount=None,
        target_allocation=position.allocation,
        reference_ids=position.reference_ids,
        priority_group=4,
        priority_score=position.allocation,
    )


def _order_action_candidates(
    candidates: list[_PortfolioActionCandidate],
) -> list[_PortfolioActionCandidate]:
    ordered = sorted(
        candidates,
        key=lambda candidate: (
            candidate.priority_group,
            -candidate.priority_score,
            candidate.ticker,
        ),
    )
    return ordered


def _round_money(amount: Decimal) -> float:
    return float(amount.quantize(_MONEY_QUANTUM))


def _finalize_portfolio(
    *,
    country: str,
    investor_theme: str,
    construction_mode: models_construction.PortfolioConstructionMode,
    verified_portfolio: portfolio_verification.VerifiedPortfolio | None,
    plan: _PortfolioConstructionPlan,
    research: _PortfolioResearch,
    draft: _PortfolioConstructionDraft,
    target_positions: list[models_construction.PortfolioTargetPosition],
    calculated_actions: _CalculatedActions | None,
    action_plan_draft: _PortfolioActionPlanDraft | None,
) -> models_construction.PortfolioConstruction:
    _validate_draft_against_research(draft, research)
    if (calculated_actions is None) != (action_plan_draft is None):
        raise PortfolioConstructionAIError("Portfolio construction action-plan state is inconsistent")
    try:
        action_plan = None
        action_data_gaps = ["Investment budget and current holdings were not supplied; an action plan cannot be built."]
        if calculated_actions is not None and action_plan_draft is not None:
            candidate_by_id = {candidate.action_id: candidate for candidate in calculated_actions.candidates}
            action_steps = []
            for reasoning in sorted(
                action_plan_draft.steps,
                key=lambda item: item.priority,
            ):
                candidate = candidate_by_id[reasoning.action_id]
                action_steps.append(
                    models_construction.PortfolioActionStep(
                        priority=reasoning.priority,
                        action=candidate.action,
                        ticker=candidate.ticker,
                        company_name=candidate.company_name,
                        instruction=candidate.instruction,
                        quantity=candidate.quantity,
                        market_price=candidate.market_price,
                        estimated_amount=candidate.estimated_amount,
                        target_allocation=candidate.target_allocation,
                        reasoning=reasoning.reasoning,
                        reference_ids=candidate.reference_ids,
                    )
                )
            action_plan = models_construction.PortfolioActionPlan(
                budget=plan.budget,
                summary=action_plan_draft.summary,
                budget_utilized=calculated_actions.budget_utilized,
                unallocated_amount=calculated_actions.unallocated_amount,
                steps=action_steps,
            )
            action_data_gaps = calculated_actions.data_gaps
        used_reference_ids = ai_reference_utils.collect_reference_ids(target_positions)
        references = [reference for reference in research.references if reference.id in used_reference_ids]
        unverified_count = sum(not reference.is_verified for reference in references)
        validation_warnings = (
            [f"{unverified_count} cited research source(s) could not be provider-verified."] if unverified_count else []
        )
        verification_data_gaps = verified_portfolio.data_gaps if verified_portfolio else []
        data_gaps = list(
            dict.fromkeys(
                [
                    *action_data_gaps,
                    *verification_data_gaps,
                    *plan.data_gaps,
                    *research.data_gaps,
                    *draft.data_gaps,
                ]
            )
        )[:20]
        return models_construction.PortfolioConstruction(
            as_of=datetime.now(UTC),
            construction_status=("CompleteWithWarnings" if validation_warnings else "Complete"),
            construction_mode=construction_mode,
            country=country,
            investor_theme=investor_theme,
            summary=draft.summary,
            verified_seed_holdings=(verified_portfolio.holdings if verified_portfolio else []),
            target_portfolio=target_positions,
            action_plan=action_plan,
            overall_data_quality=draft.overall_data_quality,
            data_gaps=data_gaps,
            validation_warnings=validation_warnings,
            references=references,
        )
    except (KeyError, ValidationError) as exc:
        raise PortfolioConstructionAIError("Portfolio construction failed final validation") from exc


def _construction_input_json(
    *,
    country: str,
    investor_theme: str,
    construction_mode: models_construction.PortfolioConstructionMode,
    verified_portfolio: portfolio_verification.VerifiedPortfolio | None,
    budget: models_construction.PortfolioBudget,
) -> str:
    return json.dumps(
        {
            "country": country,
            "investor_theme": investor_theme,
            "construction_mode": construction_mode,
            "budget": budget.model_dump(mode="json"),
            "verified_seed_portfolio": (verified_portfolio.model_dump(mode="json") if verified_portfolio else None),
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
    country: str,
    investor_theme: str,
    construction_mode: models_construction.PortfolioConstructionMode,
    verified_portfolio: portfolio_verification.VerifiedPortfolio | None,
    budget: models_construction.PortfolioBudget,
    plan: _PortfolioConstructionPlan,
    research: _PortfolioResearch,
    draft: _PortfolioConstructionDraft,
    verified_quotes: portfolio_verification.VerifiedSecurityQuotes | None,
) -> str:
    return cache.generate_key(
        _FINAL_CACHE_NAMESPACE,
        _construction_input_json(
            country=country,
            investor_theme=investor_theme,
            construction_mode=construction_mode,
            verified_portfolio=verified_portfolio,
            budget=budget,
        ),
        json.dumps(
            {
                "plan": plan.model_dump(mode="json"),
                "research": research.model_dump(mode="json"),
                "draft": draft.model_dump(mode="json"),
                "verified_target_quotes": (verified_quotes.model_dump(mode="json") if verified_quotes else None),
            },
            sort_keys=True,
        ),
        date.today().isoformat(),
        ai_prompt_utils.load_prompt(_PLAN_PROMPT),
        ai_prompt_utils.load_prompt(_RESEARCH_PROMPT),
        ai_prompt_utils.load_prompt(_CONSTRUCT_PROMPT),
        ai_prompt_utils.load_prompt(_ACTION_PLAN_PROMPT),
        json.dumps(_PortfolioConstructionPlan.model_json_schema(), sort_keys=True),
        json.dumps(_PortfolioResearchDraft.model_json_schema(), sort_keys=True),
        json.dumps(_PortfolioConstructionDraft.model_json_schema(), sort_keys=True),
        json.dumps(_PortfolioActionPlanDraft.model_json_schema(), sort_keys=True),
        json.dumps(
            models_construction.PortfolioConstruction.model_json_schema(),
            sort_keys=True,
        ),
        _task_cache_identity(_PLAN_TASK),
        _task_cache_identity(_RESEARCH_TASK),
        _task_cache_identity(_CONSTRUCT_TASK),
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


def _cached_plan(value: object) -> _PortfolioConstructionPlan:
    try:
        return (
            value.model_copy(deep=True)
            if isinstance(value, _PortfolioConstructionPlan)
            else _PortfolioConstructionPlan.model_validate(value)
        )
    except (TypeError, ValidationError) as exc:
        raise RuntimeError("Portfolio construction planning cache contains an invalid value") from exc


def _cached_research(value: object) -> _PortfolioResearch:
    try:
        return (
            value.model_copy(deep=True)
            if isinstance(value, _PortfolioResearch)
            else _PortfolioResearch.model_validate(value)
        )
    except (TypeError, ValidationError) as exc:
        raise RuntimeError("Portfolio construction research cache contains an invalid value") from exc


def _cached_draft(value: object) -> _PortfolioConstructionDraft:
    try:
        return (
            value.model_copy(deep=True)
            if isinstance(value, _PortfolioConstructionDraft)
            else _PortfolioConstructionDraft.model_validate(value)
        )
    except (TypeError, ValidationError) as exc:
        raise RuntimeError("Portfolio construction draft cache contains an invalid value") from exc


def _cached_action_plan(value: object) -> _PortfolioActionPlanDraft:
    try:
        return (
            value.model_copy(deep=True)
            if isinstance(value, _PortfolioActionPlanDraft)
            else _PortfolioActionPlanDraft.model_validate(value)
        )
    except (TypeError, ValidationError) as exc:
        raise RuntimeError("Portfolio construction action-plan cache contains an invalid value") from exc


def _cached_final(value: object) -> models_construction.PortfolioConstruction:
    try:
        return (
            value.model_copy(deep=True)
            if isinstance(value, models_construction.PortfolioConstruction)
            else models_construction.PortfolioConstruction.model_validate(value)
        )
    except (TypeError, ValidationError) as exc:
        raise RuntimeError("Portfolio construction cache contains an invalid value") from exc
