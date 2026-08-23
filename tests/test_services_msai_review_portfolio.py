import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from app.models import ai_portfolio_review as models_review
from app.services import ai_helper, portfolio_budget, portfolio_verification
from app.services import msai_review_portfolio as service
from tests import portfolio_review_fixtures as fixtures


def _major_assessment() -> service._PortfolioAssessmentDraft:
    data = fixtures.assessment_data()
    data["holding_reviews"][2]["recommendation"] = "EXIT"
    data["holding_reviews"][2]["exit_reason"] = "CriticalRisk"
    return service._PortfolioAssessmentDraft.model_validate(data)


def _major_target() -> service._PortfolioTargetDraft:
    data = fixtures.target_data()
    data["positions"] = [
        {
            **data["positions"][0],
            "allocation": 0.6,
        },
        {
            **data["positions"][1],
            "allocation": 0.4,
        },
    ]
    return service._PortfolioTargetDraft.model_validate(data)


def _addition_target_positions() -> list[models_review.PortfolioReviewTargetPosition]:
    current = fixtures.snapshot().holdings
    return [
        models_review.PortfolioReviewTargetPosition(
            ticker=holding.ticker,
            company_name=holding.company_name,
            current_allocation=holding.current_allocation,
            target_allocation=allocation,
            role=role,
            rationale="Retain the current holding at a lower aspirational weight.",
            reference_ids=[source_id],
        )
        for holding, allocation, role, source_id in zip(
            current,
            [0.45, 0.27, 0.18],
            [
                "🚀 Core growth compounder",
                "🛡️ Defensive earnings quality",
                "🧭 Digital portfolio diversifier",
            ],
            fixtures.SOURCE_IDS,
            strict=True,
        )
    ] + [
        models_review.PortfolioReviewTargetPosition(
            ticker="NASDAQ:NVDA",
            company_name="NVIDIA Corporation",
            current_allocation=0,
            target_allocation=0.1,
            role="⚡ Tactical growth catalyst",
            rationale="A researched addition diversifies the opportunity set.",
            reference_ids=[fixtures.SOURCE_IDS[0]],
        )
    ]


def _addition_quotes(price: float = 250) -> portfolio_verification.VerifiedSecurityQuotes:
    return portfolio_verification.VerifiedSecurityQuotes(
        as_of=fixtures.snapshot().as_of,
        country="US",
        currency="USD",
        securities=[
            portfolio_verification.VerifiedSecurityQuote(
                ticker="NASDAQ:NVDA",
                company_name="NVIDIA Corporation",
                exchange="NASDAQ",
                currency="USD",
                market_price=price,
            )
        ],
    )


@pytest.mark.parametrize(
    ("theme", "expected"),
    [
        ("Build durable quality exposure", "LongTerm"),
        ("Long-term buy-and-hold growth", "LongTerm"),
        ("Swing trading over days to weeks", "Swing"),
        ("Short-term trading horizon of 10 days", "Swing"),
    ],
)
def test_extract_strategy(theme, expected):
    assert service.extract_strategy(theme) == expected


def test_extract_strategy_rejects_conflicting_explicit_cues():
    with pytest.raises(portfolio_verification.PortfolioInputError, match="conflicting"):
        service.extract_strategy("Long-term core holdings plus swing trading")


def test_research_reference_repair_removes_orphans_and_unsupported_claims():
    data = fixtures.research_response_data()
    data["claims"][0]["reference_ids"].append("https://missing.example/source")
    data["claims"].append(
        {
            "category": "Issuer",
            "text": "Unsupported claim.",
            "affected_tickers": ["NASDAQ:AAPL"],
            "reference_ids": ["https://missing.example/only"],
        }
    )
    raw = service._PortfolioResearchResponse.model_validate(data)

    repaired = service._repair_research_references(raw)

    assert len(repaired.claims) == 3
    assert repaired.claims[0].reference_ids == [fixtures.SOURCE_URLS[0]]
    assert "Removed 1 unsupported claim" in repaired.data_gaps[-1]


def test_long_term_actions_hold_overweight_positions_without_trim():
    calculated = service._calculate_actions(
        snapshot=fixtures.snapshot(),
        target_positions=fixtures.target_positions(),
        holding_reviews=fixtures.holding_reviews(),
        verified_addition_quotes=None,
        budget=fixtures.total_budget(),
        strategy="LongTerm",
    )

    assert not any(candidate.action == "TRIM" for candidate in calculated.candidates)
    assert next(candidate.action for candidate in calculated.candidates if candidate.ticker == "NASDAQ:MSFT") == "HOLD"
    assert calculated.cash_ledger.purchase_spend == 400
    assert calculated.cash_ledger.unallocated_cash == 100


def test_swing_actions_include_exit_trim_buy_more_and_introduction():
    snapshot = fixtures.snapshot()
    target_positions = [
        _addition_target_positions()[0].model_copy(update={"target_allocation": 0.3}),
        _addition_target_positions()[1].model_copy(update={"target_allocation": 0.3}),
        _addition_target_positions()[3].model_copy(update={"target_allocation": 0.4}),
    ]
    holding_reviews = fixtures.holding_reviews()
    holding_reviews[2] = holding_reviews[2].model_copy(
        update={
            "target_allocation": 0,
            "recommendation": "EXIT",
            "exit_reason": "CriticalRisk",
        }
    )

    calculated = service._calculate_actions(
        snapshot=snapshot,
        target_positions=target_positions,
        holding_reviews=holding_reviews,
        verified_addition_quotes=_addition_quotes(price=100),
        budget=fixtures.total_budget(),
        strategy="Swing",
    )

    actions = {candidate.action for candidate in calculated.candidates}
    assert actions == {"EXIT", "TRIM", "BUY_MORE", "INTRODUCE"}
    assert calculated.cash_ledger.estimated_sale_proceeds == 600
    assert (
        calculated.cash_ledger.new_money_budget + calculated.cash_ledger.estimated_sale_proceeds
        == calculated.cash_ledger.purchase_spend + calculated.cash_ledger.unallocated_cash
    )


def test_inferred_budget_rises_to_fifteen_percent_only_when_it_enables_purchase():
    verified = fixtures.verified_portfolio()
    initial_budget = portfolio_budget.infer_recurring_budget(
        verified,
        rate=portfolio_budget.INFERRED_BUDGET_MIN_RATE,
    )
    target_positions = _addition_target_positions()

    resolved_budget, calculated = service._resolve_action_budget(
        verified_portfolio=verified,
        snapshot=fixtures.snapshot(),
        target_positions=target_positions,
        holding_reviews=fixtures.holding_reviews(),
        verified_addition_quotes=_addition_quotes(),
        budget=initial_budget,
        strategy="LongTerm",
    )

    assert resolved_budget.amount == 300
    assert resolved_budget.is_inferred is True
    assert any(candidate.action == "INTRODUCE" for candidate in calculated.candidates)


def test_unrequested_major_rebalance_skips_action_calculation():
    major_assessment = _major_assessment()
    major_target = _major_target()
    with (
        patch(
            "app.services.msai_review_portfolio.portfolio_verification.verify_portfolio",
            new_callable=AsyncMock,
            return_value=fixtures.verified_portfolio(),
        ),
        patch(
            "app.services.msai_review_portfolio._plan_portfolio",
            new_callable=AsyncMock,
            return_value=fixtures.plan(),
        ),
        patch(
            "app.services.msai_review_portfolio._research_portfolio",
            new_callable=AsyncMock,
            return_value=fixtures.research(),
        ),
        patch(
            "app.services.msai_review_portfolio._assess_portfolio",
            new_callable=AsyncMock,
            return_value=major_assessment,
        ),
        patch(
            "app.services.msai_review_portfolio._design_target",
            new_callable=AsyncMock,
            return_value=major_target,
        ),
        patch(
            "app.services.msai_review_portfolio._verify_addition_quotes",
            new_callable=AsyncMock,
        ) as mock_verify_additions,
        patch(
            "app.services.msai_review_portfolio._create_action_plan",
            new_callable=AsyncMock,
        ) as mock_action_plan,
        patch(
            "app.services.msai_review_portfolio.cache.get",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "app.services.msai_review_portfolio.cache.set",
            new_callable=AsyncMock,
            return_value=True,
        ),
    ):
        result = asyncio.run(
            service.ai_review_portfolio(
                fixtures.holdings(),
                country="US",
                investor_theme="Long-term growth. Total budget USD 500.",
                rebalance_plan=False,
            )
        )

    assert result.rebalance_recommended == "YES"
    assert result.target_turnover == pytest.approx(0.2)
    assert result.action_plan is None
    mock_verify_additions.assert_not_awaited()
    mock_action_plan.assert_not_awaited()


def test_structured_review_runs_all_five_stages_and_returns_growth_plan():
    theme = "Long-term growth. Total budget USD 500."
    action_draft = service._PortfolioActionPlanDraft(
        summary="Buy underweight positions and retain residual cash.",
        actions=[
            service._PortfolioActionReasoning(
                action_id="buy_more:NASDAQ:AAPL",
                priority=1,
                reasoning="Increase the highest-priority underweight core holding.",
            ),
            service._PortfolioActionReasoning(
                action_id="buy_more:NASDAQ:GOOGL",
                priority=2,
                reasoning="Add one whole share toward the validated target.",
            ),
            service._PortfolioActionReasoning(
                action_id="hold:NASDAQ:MSFT",
                priority=3,
                reasoning="Hold the aligned overweight position and direct new cash elsewhere.",
            ),
        ],
    )
    responses = [
        ai_helper.LLMResponse(completion=fixtures.plan(portfolio_id="portfolio-id").model_dump_json()),
        ai_helper.LLMResponse(
            completion=json.dumps(fixtures.research_response_data(portfolio_id="portfolio-id")),
            citation_urls=fixtures.SOURCE_URLS,
        ),
        ai_helper.LLMResponse(completion=json.dumps(fixtures.assessment_data(portfolio_id="portfolio-id"))),
        ai_helper.LLMResponse(completion=json.dumps(fixtures.target_data(portfolio_id="portfolio-id"))),
        ai_helper.LLMResponse(completion=action_draft.model_dump_json()),
    ]

    with (
        patch(
            "app.services.msai_review_portfolio.portfolio_verification.verify_portfolio",
            new_callable=AsyncMock,
            return_value=fixtures.verified_portfolio(),
        ),
        patch(
            "app.services.msai_review_portfolio.ai_helper.ai_exec_task",
            new_callable=AsyncMock,
            side_effect=responses,
        ) as mock_ai_exec,
        patch(
            "app.services.msai_review_portfolio.cache.generate_key",
            return_value="portfolio-id",
        ),
        patch(
            "app.services.msai_review_portfolio.cache.get",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "app.services.msai_review_portfolio.cache.set",
            new_callable=AsyncMock,
            return_value=True,
        ),
    ):
        result = asyncio.run(
            service.ai_review_portfolio(
                fixtures.holdings(),
                country="US",
                investor_theme=theme,
            )
        )

    assert result.result_type == "PortfolioReview"
    assert result.strategy == "LongTerm"
    assert result.rebalance_recommended == "NO"
    assert result.action_plan is not None
    assert result.action_plan.plan_type == "Growth"
    assert [action.action for action in result.action_plan.actions] == [
        "BUY_MORE",
        "BUY_MORE",
        "HOLD",
    ]
    assert result.action_plan.cash_ledger.purchase_spend == 400
    assert all(reference.is_verified for reference in result.references)
    assert [call.args[0] for call in mock_ai_exec.await_args_list] == [
        "REVIEW_PORTFOLIO_PLAN",
        "REVIEW_PORTFOLIO_RESEARCH",
        "REVIEW_PORTFOLIO_ASSESS",
        "REVIEW_PORTFOLIO_TARGET",
        "REVIEW_PORTFOLIO_ACTION_PLAN",
    ]


def test_provider_failure_is_explicit():
    with (
        patch(
            "app.services.msai_review_portfolio.portfolio_verification.verify_portfolio",
            new_callable=AsyncMock,
            return_value=fixtures.verified_portfolio(),
        ),
        patch(
            "app.services.msai_review_portfolio.ai_helper.ai_exec_task",
            new_callable=AsyncMock,
            return_value=ai_helper.LLMResponse(is_error=True, error_msg="provider failed"),
        ),
        patch(
            "app.services.msai_review_portfolio.cache.get",
            new_callable=AsyncMock,
            return_value=None,
        ),
    ):
        with pytest.raises(service.PortfolioReviewAIError, match="planning failed"):
            asyncio.run(
                service.ai_review_portfolio(
                    fixtures.holdings(),
                    country="US",
                    investor_theme="Long-term growth. Total budget USD 500.",
                )
            )


def test_all_provider_response_schema_properties_are_required():
    def assert_required_properties(value: object) -> None:
        if isinstance(value, dict):
            if "properties" in value:
                assert set(value["properties"]) == set(value.get("required", []))
            for nested in value.values():
                assert_required_properties(nested)
        elif isinstance(value, list):
            for nested in value:
                assert_required_properties(nested)

    for response_model in (
        service._PortfolioReviewPlan,
        service._PortfolioResearchResponse,
        service._PortfolioAssessmentDraft,
        service._PortfolioTargetDraft,
        service._PortfolioActionPlanDraft,
    ):
        assert_required_properties(response_model.model_json_schema())
