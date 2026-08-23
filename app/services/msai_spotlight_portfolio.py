from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Annotated, Literal, Self

import openai
from pydantic import Field, ValidationError, model_validator

from .. import config
from ..models import ai as models_ai
from ..models import ai_portfolio_spotlight as models_spotlight
from ..models import portfolio as models_portfolio
from ..models import types as models_types
from ..utils import ai_prompt as ai_prompt_utils
from ..utils import ai_reference as ai_reference_utils
from ..utils import cache, conv
from . import ai_helper, portfolio_verification

_PLAN_CACHE_NAMESPACE = "portfolio-spotlight-plan-v1"
_RESEARCH_CACHE_NAMESPACE = "portfolio-spotlight-research-v1"
_ASSESSMENT_CACHE_NAMESPACE = "portfolio-spotlight-assessment-v1"
_ANALYSIS_CACHE_NAMESPACE = "portfolio-spotlight-analysis-v1"
_AI_STAGE_CACHE_TTL = 60 * 60
_PLAN_TASK = "SPOTLIGHT_PORTFOLIO_PLAN"
_RESEARCH_TASK = "SPOTLIGHT_PORTFOLIO_RESEARCH"
_ASSESSMENT_TASK = "SPOTLIGHT_PORTFOLIO_ASSESS"
_PLAN_PROMPT = "portfolio_spotlight_plan.txt"
_RESEARCH_PROMPT = "portfolio_spotlight_research.txt"
_ASSESSMENT_PROMPT = "portfolio_spotlight_assessment.txt"
_PLAN_SCHEMA_NAME = "portfolio_spotlight_plan"
_RESEARCH_SCHEMA_NAME = "portfolio_spotlight_research"
_ASSESSMENT_SCHEMA_NAME = "portfolio_spotlight_assessment"

_ResearchCategory = Literal["Issuer", "Sector", "Macro", "Portfolio", "Liquidity", "Valuation"]


class PortfolioSpotlightAIError(RuntimeError):
    pass


class _PortfolioAnalysisPlan(models_ai.StrictAIModel):
    portfolio_id: models_types.NonEmptyString = Field(max_length=128)
    investor_theme_present: bool
    investor_context_summary: models_types.NonEmptyString | None = Field(max_length=2000)
    research_priorities: list[_ResearchCategory] = Field(min_length=1, max_length=6)
    assessment_focus: list[
        Annotated[
            models_types.NonEmptyString,
            Field(max_length=4000),
        ]
    ] = Field(min_length=1, max_length=10)
    investor_constraints: list[
        Annotated[
            models_types.NonEmptyString,
            Field(max_length=4000),
        ]
    ] = Field(max_length=10)
    data_gaps: list[
        Annotated[
            models_types.NonEmptyString,
            Field(max_length=4000),
        ]
    ] = Field(max_length=10)

    @model_validator(mode="after")
    def validate_plan(self) -> Self:
        if len(self.research_priorities) != len(set(self.research_priorities)):
            raise ValueError("research_priorities must be unique")
        if len(self.assessment_focus) != len(set(self.assessment_focus)):
            raise ValueError("assessment_focus must be unique")
        if len(self.investor_constraints) != len(set(self.investor_constraints)):
            raise ValueError("investor_constraints must be unique")
        if self.investor_theme_present:
            if self.investor_context_summary is None:
                raise ValueError("investor theme requires an investor context summary")
        elif self.investor_context_summary is not None or self.investor_constraints:
            raise ValueError("absent investor theme cannot produce investor context or constraints")
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
    affected_tickers: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(
        min_length=1,
        max_length=50,
    )
    reference_ids: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(
        min_length=1,
        max_length=6,
    )


class _PortfolioResearchResponse(models_ai.StrictAIModel):
    portfolio_id: models_types.NonEmptyString = Field(max_length=4000)
    as_of: datetime
    claims: list[_PortfolioResearchClaim] = Field(max_length=12)
    data_gaps: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(max_length=20)
    references: list[_PortfolioResearchSourceMetadata] = Field(max_length=6)


class _PortfolioResearchDraft(_PortfolioResearchResponse):
    @model_validator(mode="after")
    def validate_references(self) -> Self:
        ai_reference_utils.validate_reference_registry(self.references, self)
        return self


class _PortfolioResearch(_PortfolioResearchDraft):
    references: list[models_ai.ReferenceSource] = Field(max_length=6)


class _PortfolioAssessmentDraft(models_ai.StrictAIModel):
    portfolio_id: models_types.NonEmptyString = Field(max_length=4000)
    as_of: datetime
    overall_data_quality: models_types.DataQuality
    risks: list[models_spotlight.PortfolioSpotlightRiskAction] = Field(max_length=4)
    data_gaps: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(max_length=20)

    @model_validator(mode="after")
    def validate_risk_order(self) -> Self:
        _validate_risk_order(self.risks)
        return self


async def ai_spotlight_portfolio(
    *,
    portfolio: list[models_portfolio.PortfolioHolding],
    country: str,
    investor_theme: str | None = None,
) -> models_spotlight.PortfolioSpotlightAnalysis:
    """Verify and perform a quick structured review of current portfolio risks."""

    normalized_country = conv.country_to_iso2(country.strip())
    if not normalized_country:
        raise portfolio_verification.PortfolioInputError("Unsupported or unknown country")

    active_positions = [position.model_copy(deep=True) for position in portfolio if position.num_shares > 0]
    if not active_positions:
        return _empty_portfolio_analysis()

    verified_portfolio = await portfolio_verification.verify_portfolio(
        active_positions,
        country=normalized_country,
    )
    snapshot = models_spotlight.PortfolioSpotlightSnapshot.model_validate(verified_portfolio.model_dump())
    normalized_theme = (investor_theme or "").strip() or None

    analysis_cache_key = _analysis_cache_key(snapshot, normalized_theme)
    cached_analysis = await cache.get(analysis_cache_key)
    if cached_analysis is not None:
        return _cached_analysis(cached_analysis)

    portfolio_id = cache.generate_key("portfolio-spotlight-id", snapshot.model_dump_json())
    plan = await _build_analysis_plan(
        portfolio_id,
        snapshot,
        investor_theme=normalized_theme,
    )
    research = await _research_portfolio(
        portfolio_id,
        snapshot,
        plan,
        investor_theme=normalized_theme,
    )
    assessment = await _assess_portfolio(
        portfolio_id,
        snapshot,
        research,
        plan,
        investor_theme=normalized_theme,
    )
    analysis = _build_analysis(snapshot, plan, research, assessment)
    await cache.set(
        analysis_cache_key,
        analysis.model_dump(mode="json"),
        ttl=_AI_STAGE_CACHE_TTL,
    )
    return analysis


def _empty_portfolio_analysis() -> models_spotlight.PortfolioSpotlightAnalysis:
    return models_spotlight.PortfolioSpotlightAnalysis(
        as_of=datetime.now(UTC),
        analysis_status="Complete",
        portfolio_empty=True,
        overall_data_quality="Insufficient",
        snapshot=None,
        risks=[],
        rebalance_recommended="NO",
        data_gaps=["Portfolio has no positions with positive holdings."],
        validation_warnings=[],
        references=[],
    )


def _investor_theme_context(investor_theme: str | None) -> str:
    if investor_theme is None:
        return "NO_INVESTOR_THEME_SUPPLIED"
    return f"BEGIN_VALIDATED_UNTRUSTED_INVESTOR_THEME\n{investor_theme}\nEND_VALIDATED_UNTRUSTED_INVESTOR_THEME"


async def _build_analysis_plan(
    portfolio_id: str,
    snapshot: models_spotlight.PortfolioSpotlightSnapshot,
    *,
    investor_theme: str | None,
) -> _PortfolioAnalysisPlan:
    theme_present = investor_theme is not None
    prompt = ai_prompt_utils.render_prompt(
        _PLAN_PROMPT,
        {
            "PORTFOLIO_ID": portfolio_id,
            "INVESTOR_THEME_PRESENT": json.dumps(theme_present),
            "INVESTOR_THEME_CONTEXT": _investor_theme_context(investor_theme),
            "PORTFOLIO_JSON": snapshot.model_dump_json(),
        },
    )
    cache_key = cache.generate_key(
        _PLAN_CACHE_NAMESPACE,
        prompt,
        json.dumps(_PortfolioAnalysisPlan.model_json_schema(), sort_keys=True),
        _task_cache_identity(_PLAN_TASK),
    )
    cached_plan = await cache.get(cache_key)
    if cached_plan is not None:
        return _cached_plan(cached_plan)

    try:
        response = await ai_helper.ai_exec_task(
            _PLAN_TASK,
            prompt,
            country=snapshot.country,
            response_json_schema=_PortfolioAnalysisPlan.model_json_schema(),
            schema_name=_PLAN_SCHEMA_NAME,
        )
    except (OSError, ValueError, openai.APIError) as exc:
        logging.exception("[Portfolio Spotlight] Planning provider call failed.")
        raise PortfolioSpotlightAIError("Portfolio spotlight planning provider failed") from exc
    if response.is_error:
        logging.error("[Portfolio Spotlight] Planning failed: %s", response.error_msg)
        raise PortfolioSpotlightAIError("Portfolio spotlight planning failed")

    try:
        plan = _PortfolioAnalysisPlan.model_validate_json(response.completion)
        if plan.portfolio_id != portfolio_id:
            raise ValueError("planning returned a different portfolio ID")
        if plan.investor_theme_present != theme_present:
            raise ValueError("planning returned an inconsistent investor theme state")
    except (ValueError, ValidationError) as exc:
        raise PortfolioSpotlightAIError("Portfolio spotlight planning returned invalid structured data") from exc

    await cache.set(
        cache_key,
        plan.model_dump(mode="json"),
        ttl=_AI_STAGE_CACHE_TTL,
    )
    return plan


async def _research_portfolio(
    portfolio_id: str,
    snapshot: models_spotlight.PortfolioSpotlightSnapshot,
    plan: _PortfolioAnalysisPlan,
    *,
    investor_theme: str | None,
) -> _PortfolioResearch:
    prompt = ai_prompt_utils.render_prompt(
        _RESEARCH_PROMPT,
        {
            "PORTFOLIO_ID": portfolio_id,
            "PORTFOLIO_JSON": json.dumps(
                {
                    "investor_theme": investor_theme,
                    "snapshot": snapshot.model_dump(mode="json"),
                },
                sort_keys=True,
            ),
            "PLAN_JSON": plan.model_dump_json(),
        },
    )
    cache_key = cache.generate_key(
        _RESEARCH_CACHE_NAMESPACE,
        prompt,
        json.dumps(_PortfolioResearchDraft.model_json_schema(), sort_keys=True),
        _task_cache_identity(_RESEARCH_TASK),
    )
    cached_research = await cache.get(cache_key)
    if cached_research is not None:
        return _cached_research(cached_research)

    try:
        response = await ai_helper.ai_exec_task(
            _RESEARCH_TASK,
            prompt,
            country=snapshot.country,
            response_json_schema=_PortfolioResearchDraft.model_json_schema(),
            schema_name=_RESEARCH_SCHEMA_NAME,
        )
    except (OSError, ValueError, openai.APIError) as exc:
        logging.exception("[Portfolio Spotlight] Research provider call failed.")
        raise PortfolioSpotlightAIError("Portfolio spotlight research provider failed") from exc
    if response.is_error:
        logging.error("[Portfolio Spotlight] Research failed: %s", response.error_msg)
        raise PortfolioSpotlightAIError("Portfolio spotlight research failed")

    try:
        raw_research = _PortfolioResearchResponse.model_validate_json(response.completion)
        if raw_research.portfolio_id != portfolio_id:
            raise ValueError("research returned a different portfolio ID")
        _validate_claim_tickers(raw_research.claims, snapshot)
        repaired_research = _repair_research_references(raw_research)
        research = _finalize_research_references(
            repaired_research,
            response.citation_urls,
            accessed_at=datetime.now(UTC),
        )
    except (TypeError, ValueError, ValidationError) as exc:
        raise PortfolioSpotlightAIError("Portfolio spotlight research returned invalid structured data") from exc

    await cache.set(
        cache_key,
        research.model_dump(mode="json"),
        ttl=_AI_STAGE_CACHE_TTL,
    )
    return research


def _validate_claim_tickers(
    claims: list[_PortfolioResearchClaim],
    snapshot: models_spotlight.PortfolioSpotlightSnapshot,
) -> None:
    known_tickers = {holding.ticker for holding in snapshot.holdings}
    unknown_tickers = {ticker for claim in claims for ticker in claim.affected_tickers if ticker not in known_tickers}
    if unknown_tickers:
        raise ValueError(f"research contains unknown tickers: {sorted(unknown_tickers)}")


def _repair_research_references(
    research: _PortfolioResearchResponse,
) -> _PortfolioResearchDraft:
    research_data = research.model_dump()
    registry_ids = {reference.id for reference in research.references}
    missing_ids: set[str] = set()
    repaired_claims = []
    dropped_claims = 0

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
    used_ids = ai_reference_utils.collect_reference_ids(research_data)
    research_data["references"] = [
        reference for reference in research_data["references"] if reference["id"] in used_ids
    ]
    if missing_ids or dropped_claims:
        missing_text = ", ".join(sorted(missing_ids)) or "none"
        warning = f"Ignored missing source IDs: {missing_text}."
        if dropped_claims:
            warning += f" Removed {dropped_claims} unsupported claim(s)."
        research_data["data_gaps"] = [*research_data["data_gaps"][:19], warning]
        logging.warning("[Portfolio Spotlight] %s", warning)
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


async def _assess_portfolio(
    portfolio_id: str,
    snapshot: models_spotlight.PortfolioSpotlightSnapshot,
    research: _PortfolioResearch,
    plan: _PortfolioAnalysisPlan,
    *,
    investor_theme: str | None,
) -> _PortfolioAssessmentDraft:
    prompt = ai_prompt_utils.render_prompt(
        _ASSESSMENT_PROMPT,
        {
            "PORTFOLIO_ID": portfolio_id,
            "PORTFOLIO_JSON": json.dumps(
                {
                    "investor_theme": investor_theme,
                    "snapshot": snapshot.model_dump(mode="json"),
                },
                sort_keys=True,
            ),
            "PLAN_JSON": plan.model_dump_json(),
            "RESEARCH_JSON": research.model_dump_json(),
        },
    )
    cache_key = cache.generate_key(
        _ASSESSMENT_CACHE_NAMESPACE,
        prompt,
        json.dumps(_PortfolioAssessmentDraft.model_json_schema(), sort_keys=True),
        _task_cache_identity(_ASSESSMENT_TASK),
    )
    cached_assessment = await cache.get(cache_key)
    if cached_assessment is not None:
        return _cached_assessment(cached_assessment)

    try:
        response = await ai_helper.ai_exec_task(
            _ASSESSMENT_TASK,
            prompt,
            country=snapshot.country,
            response_json_schema=_PortfolioAssessmentDraft.model_json_schema(),
            schema_name=_ASSESSMENT_SCHEMA_NAME,
        )
    except (OSError, ValueError, openai.APIError) as exc:
        logging.exception("[Portfolio Spotlight] Assessment provider call failed.")
        raise PortfolioSpotlightAIError("Portfolio spotlight assessment provider failed") from exc
    if response.is_error:
        logging.error("[Portfolio Spotlight] Assessment failed: %s", response.error_msg)
        raise PortfolioSpotlightAIError("Portfolio spotlight assessment failed")

    try:
        assessment = _PortfolioAssessmentDraft.model_validate_json(response.completion)
        if assessment.portfolio_id != portfolio_id:
            raise ValueError("assessment returned a different portfolio ID")
        _validate_assessment(assessment, snapshot, research)
    except (ValueError, ValidationError) as exc:
        raise PortfolioSpotlightAIError("Portfolio spotlight assessment returned invalid structured data") from exc

    await cache.set(
        cache_key,
        assessment.model_dump(mode="json"),
        ttl=_AI_STAGE_CACHE_TTL,
    )
    return assessment


def _validate_assessment(
    assessment: _PortfolioAssessmentDraft,
    snapshot: models_spotlight.PortfolioSpotlightSnapshot,
    research: _PortfolioResearch,
) -> None:
    known_tickers = {holding.ticker for holding in snapshot.holdings}
    unknown_tickers = {
        ticker for risk in assessment.risks for ticker in risk.affected_tickers if ticker not in known_tickers
    }
    if unknown_tickers:
        raise ValueError(f"assessment contains unknown tickers: {sorted(unknown_tickers)}")

    known_reference_ids = {reference.id for reference in research.references}
    unknown_reference_ids = ai_reference_utils.collect_reference_ids(assessment) - known_reference_ids
    if unknown_reference_ids:
        raise ValueError(f"assessment contains unknown reference IDs: {sorted(unknown_reference_ids)}")


def _validate_risk_order(
    risks: list[models_spotlight.PortfolioSpotlightRiskAction],
) -> None:
    expected_ranks = list(range(1, len(risks) + 1))
    if [risk.rank for risk in risks] != expected_ranks:
        raise ValueError("risk ranks must be consecutive and start at one")
    level_order = {"Critical": 0, "High": 1, "Medium": 2}
    order = [level_order[risk.level] for risk in risks]
    if order != sorted(order):
        raise ValueError("risks must be ordered from highest to lowest level")


def _build_analysis(
    snapshot: models_spotlight.PortfolioSpotlightSnapshot,
    plan: _PortfolioAnalysisPlan,
    research: _PortfolioResearch,
    assessment: _PortfolioAssessmentDraft,
) -> models_spotlight.PortfolioSpotlightAnalysis:
    used_reference_ids = ai_reference_utils.collect_reference_ids(assessment)
    references = [reference for reference in research.references if reference.id in used_reference_ids]
    unverified_count = sum(not reference.is_verified for reference in references)
    warnings = []
    if unverified_count:
        warnings.append(f"{unverified_count} cited research source(s) could not be provider-verified.")
    rebalance_recommended: models_spotlight.PortfolioSpotlightRebalanceFlag = (
        "YES" if any(risk.requires_rebalance for risk in assessment.risks) else "NO"
    )
    data_gaps = list(
        dict.fromkeys(
            [
                *snapshot.data_gaps,
                *plan.data_gaps,
                *research.data_gaps,
                *assessment.data_gaps,
            ]
        )
    )[:20]
    try:
        return models_spotlight.PortfolioSpotlightAnalysis(
            as_of=datetime.now(UTC),
            analysis_status="CompleteWithWarnings" if warnings else "Complete",
            portfolio_empty=False,
            overall_data_quality=assessment.overall_data_quality,
            snapshot=snapshot,
            risks=assessment.risks,
            rebalance_recommended=rebalance_recommended,
            data_gaps=data_gaps,
            validation_warnings=warnings,
            references=references,
        )
    except ValidationError as exc:
        raise PortfolioSpotlightAIError("Portfolio spotlight failed final validation") from exc


def _analysis_cache_key(
    snapshot: models_spotlight.PortfolioSpotlightSnapshot,
    investor_theme: str | None,
) -> str:
    return cache.generate_key(
        _ANALYSIS_CACHE_NAMESPACE,
        snapshot.model_dump_json(),
        json.dumps({"investor_theme": investor_theme}, sort_keys=True),
        ai_prompt_utils.load_prompt(_PLAN_PROMPT),
        ai_prompt_utils.load_prompt(_RESEARCH_PROMPT),
        ai_prompt_utils.load_prompt(_ASSESSMENT_PROMPT),
        json.dumps(_PortfolioAnalysisPlan.model_json_schema(), sort_keys=True),
        json.dumps(_PortfolioResearchDraft.model_json_schema(), sort_keys=True),
        json.dumps(_PortfolioAssessmentDraft.model_json_schema(), sort_keys=True),
        json.dumps(models_spotlight.PortfolioSpotlightAnalysis.model_json_schema(), sort_keys=True),
        _task_cache_identity(_PLAN_TASK),
        _task_cache_identity(_RESEARCH_TASK),
        _task_cache_identity(_ASSESSMENT_TASK),
    )


def _task_cache_identity(task_id: str) -> str:
    task_config = config.settings_llm_task.tasks.get(task_id)
    if task_config is None:
        return task_id
    return json.dumps(
        {
            "task": task_id,
            "vendor": task_config.vendor,
            "tier": task_config.tier,
            "model": task_config.model,
            "reasoning_effort": task_config.reasoning_effort,
            "use_web_search": task_config.use_web_search,
            "max_tool_calls": task_config.max_tool_calls,
        },
        sort_keys=True,
    )


def _cached_plan(value: object) -> _PortfolioAnalysisPlan:
    try:
        return (
            value.model_copy(deep=True)
            if isinstance(value, _PortfolioAnalysisPlan)
            else _PortfolioAnalysisPlan.model_validate(value)
        )
    except (TypeError, ValidationError) as exc:
        raise RuntimeError("Portfolio spotlight planning cache contains an invalid value") from exc


def _cached_research(value: object) -> _PortfolioResearch:
    try:
        return (
            value.model_copy(deep=True)
            if isinstance(value, _PortfolioResearch)
            else _PortfolioResearch.model_validate(value)
        )
    except (TypeError, ValidationError) as exc:
        raise RuntimeError("Portfolio spotlight research cache contains an invalid value") from exc


def _cached_assessment(value: object) -> _PortfolioAssessmentDraft:
    try:
        return (
            value.model_copy(deep=True)
            if isinstance(value, _PortfolioAssessmentDraft)
            else _PortfolioAssessmentDraft.model_validate(value)
        )
    except (TypeError, ValidationError) as exc:
        raise RuntimeError("Portfolio spotlight assessment cache contains an invalid value") from exc


def _cached_analysis(value: object) -> models_spotlight.PortfolioSpotlightAnalysis:
    try:
        return (
            value.model_copy(deep=True)
            if isinstance(value, models_spotlight.PortfolioSpotlightAnalysis)
            else models_spotlight.PortfolioSpotlightAnalysis.model_validate(value)
        )
    except (TypeError, ValidationError) as exc:
        raise RuntimeError("Portfolio spotlight analysis cache contains an invalid value") from exc
