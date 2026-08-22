from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime
from typing import Annotated, Self

import openai
from pydantic import Field, ValidationError, field_validator, model_validator

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

_PLAN_PROMPT = "portfolio_construction_plan.txt"
_RESEARCH_PROMPT = "portfolio_construction_research.txt"
_CONSTRUCT_PROMPT = "portfolio_construction_construct.txt"

_PLAN_SCHEMA_NAME = "portfolio_construction_plan"
_RESEARCH_SCHEMA_NAME = "portfolio_construction_research"
_CONSTRUCT_SCHEMA_NAME = "portfolio_construction_target"

_PLAN_CACHE_NAMESPACE = "portfolio-construction-plan-v1"
_RESEARCH_CACHE_NAMESPACE = "portfolio-construction-research-v1"
_CONSTRUCT_CACHE_NAMESPACE = "portfolio-construction-draft-v1"
_FINAL_CACHE_NAMESPACE = "portfolio-construction-final-v1"
_AI_STAGE_CACHE_TTL = 60 * 60
_ALLOCATION_TOLERANCE = 0.01


class PortfolioConstructionAIError(RuntimeError):
    pass


class _PortfolioConstructionPlan(models_ai.StrictAIModel):
    construction_mode: models_construction.PortfolioConstructionMode
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
    construction_mode: models_construction.PortfolioConstructionMode = "Seeded" if active_positions else "Scratch"
    verified_portfolio = (
        await portfolio_verification.verify_portfolio(
            active_positions,
            country=normalized_country,
        )
        if active_positions
        else None
    )

    final_cache_key = _final_cache_key(
        country=normalized_country,
        investor_theme=normalized_theme,
        construction_mode=construction_mode,
        verified_portfolio=verified_portfolio,
    )
    cached_construction = await cache.get(final_cache_key)
    if cached_construction is not None:
        return _cached_final(cached_construction)

    plan = await _plan_portfolio(
        country=normalized_country,
        investor_theme=normalized_theme,
        construction_mode=construction_mode,
        verified_portfolio=verified_portfolio,
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
    construction = _finalize_portfolio(
        country=normalized_country,
        investor_theme=normalized_theme,
        construction_mode=construction_mode,
        verified_portfolio=verified_portfolio,
        plan=plan,
        research=research,
        draft=draft,
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
) -> _PortfolioConstructionPlan:
    prompt = ai_prompt_utils.render_prompt(
        _PLAN_PROMPT,
        {
            "CONSTRUCTION_INPUT_JSON": _construction_input_json(
                country=country,
                investor_theme=investor_theme,
                construction_mode=construction_mode,
                verified_portfolio=verified_portfolio,
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


def _finalize_portfolio(
    *,
    country: str,
    investor_theme: str,
    construction_mode: models_construction.PortfolioConstructionMode,
    verified_portfolio: portfolio_verification.VerifiedPortfolio | None,
    plan: _PortfolioConstructionPlan,
    research: _PortfolioResearch,
    draft: _PortfolioConstructionDraft,
) -> models_construction.PortfolioConstruction:
    _validate_draft_against_research(draft, research)
    candidates = {candidate.ticker: candidate for candidate in research.candidates}
    allocation_total = sum(position.allocation for position in draft.positions)
    target_positions = [
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
                ("Investment amount was not supplied; target allocations cannot be converted to execution quantities."),
                *verification_data_gaps,
                *plan.data_gaps,
                *research.data_gaps,
                *draft.data_gaps,
            ]
        )
    )[:20]

    try:
        return models_construction.PortfolioConstruction(
            as_of=datetime.now(UTC),
            construction_status=("CompleteWithWarnings" if validation_warnings else "Complete"),
            construction_mode=construction_mode,
            country=country,
            investor_theme=investor_theme,
            summary=draft.summary,
            verified_seed_holdings=(verified_portfolio.holdings if verified_portfolio else []),
            target_portfolio=target_positions,
            overall_data_quality=draft.overall_data_quality,
            data_gaps=data_gaps,
            validation_warnings=validation_warnings,
            references=references,
        )
    except ValidationError as exc:
        raise PortfolioConstructionAIError("Portfolio construction failed final validation") from exc


def _construction_input_json(
    *,
    country: str,
    investor_theme: str,
    construction_mode: models_construction.PortfolioConstructionMode,
    verified_portfolio: portfolio_verification.VerifiedPortfolio | None,
) -> str:
    return json.dumps(
        {
            "country": country,
            "investor_theme": investor_theme,
            "construction_mode": construction_mode,
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
) -> str:
    return cache.generate_key(
        _FINAL_CACHE_NAMESPACE,
        _construction_input_json(
            country=country,
            investor_theme=investor_theme,
            construction_mode=construction_mode,
            verified_portfolio=verified_portfolio,
        ),
        date.today().isoformat(),
        ai_prompt_utils.load_prompt(_PLAN_PROMPT),
        ai_prompt_utils.load_prompt(_RESEARCH_PROMPT),
        ai_prompt_utils.load_prompt(_CONSTRUCT_PROMPT),
        json.dumps(_PortfolioConstructionPlan.model_json_schema(), sort_keys=True),
        json.dumps(_PortfolioResearchDraft.model_json_schema(), sort_keys=True),
        json.dumps(_PortfolioConstructionDraft.model_json_schema(), sort_keys=True),
        json.dumps(
            models_construction.PortfolioConstruction.model_json_schema(),
            sort_keys=True,
        ),
        _task_cache_identity(_PLAN_TASK),
        _task_cache_identity(_RESEARCH_TASK),
        _task_cache_identity(_CONSTRUCT_TASK),
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


def _cached_final(value: object) -> models_construction.PortfolioConstruction:
    try:
        return (
            value.model_copy(deep=True)
            if isinstance(value, models_construction.PortfolioConstruction)
            else models_construction.PortfolioConstruction.model_validate(value)
        )
    except (TypeError, ValidationError) as exc:
        raise RuntimeError("Portfolio construction cache contains an invalid value") from exc
