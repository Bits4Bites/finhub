import asyncio
from decimal import Decimal
from unittest import mock

import pytest

from app.models import portfolio as models_portfolio
from app.services import ai_helper, portfolio_budget, portfolio_verification
from app.services import msai_review_portfolio as service
from tests import portfolio_review_fixtures as fixtures
from tests import portfolio_service_fixtures as boundaries

_DEFAULT_PRICES = {
    "NASDAQ:AAPL": 100,
    "NASDAQ:MSFT": 120,
    "NASDAQ:GOOGL": 100,
    "NASDAQ:NVDA": 250,
}
_COMPANY_NAMES = {
    "NASDAQ:AAPL": "Apple Inc.",
    "NASDAQ:MSFT": "Microsoft Corporation",
    "NASDAQ:GOOGL": "Alphabet Inc.",
    "NASDAQ:NVDA": "NVIDIA Corporation",
}


def _review_ai(
    *,
    budget,
    strategy="LongTerm",
    research_data: dict[str, object] | None = None,
    assessment_data: dict[str, object] | None = None,
    target_data: dict[str, object] | None = None,
    citation_urls: tuple[str, ...] = tuple(fixtures.SOURCE_URLS),
) -> boundaries.QueuedAI:
    portfolio_id = boundaries.PORTFOLIO_ID
    return boundaries.QueuedAI(
        boundaries.AIResponse(
            fixtures.plan_data(
                portfolio_id=portfolio_id,
                budget=budget,
                strategy=strategy,
            )
        ),
        boundaries.AIResponse(
            research_data or fixtures.research_response_data(portfolio_id=portfolio_id),
            citation_urls=citation_urls,
        ),
        boundaries.AIResponse(assessment_data or fixtures.assessment_data(portfolio_id=portfolio_id)),
        boundaries.AIResponse(target_data or fixtures.target_data(portfolio_id=portfolio_id)),
        boundaries.AIResponse(
            {
                "summary": "Implement the validated actions in priority order.",
                "actions": boundaries.ACTION_REASONING,
            }
        ),
    )


def _research_with_nvda() -> dict[str, object]:
    data = fixtures.research_response_data(portfolio_id=boundaries.PORTFOLIO_ID)
    data["additions"] = [
        {
            "ticker": "NASDAQ:NVDA",
            "company_name": "NVIDIA Corporation",
            "fit": "Adds a researched growth catalyst.",
            "key_risks": ["Valuation and execution risk."],
            "reference_ids": [fixtures.SOURCE_URLS[0]],
        }
    ]
    return data


def _assessment_with_nvda(
    *,
    exit_google: bool = False,
    exit_reason: str = "CriticalRisk",
) -> dict[str, object]:
    data = fixtures.assessment_data(portfolio_id=boundaries.PORTFOLIO_ID)
    data["eligible_additions"] = ["NASDAQ:NVDA"]
    if exit_google:
        data["holding_reviews"][2]["recommendation"] = "EXIT"
        data["holding_reviews"][2]["exit_reason"] = exit_reason
    return data


def _target_with_nvda(
    allocations: tuple[float, ...],
    *,
    retain_google: bool,
) -> dict[str, object]:
    current_positions = fixtures.target_data(portfolio_id=boundaries.PORTFOLIO_ID)["positions"]
    positions = [
        {
            **current_positions[0],
            "allocation": allocations[0],
        },
        {
            **current_positions[1],
            "allocation": allocations[1],
        },
    ]
    allocation_index = 2
    if retain_google:
        positions.append(
            {
                **current_positions[2],
                "allocation": allocations[allocation_index],
            }
        )
        allocation_index += 1
    positions.append(
        {
            "ticker": "NASDAQ:NVDA",
            "allocation": allocations[allocation_index],
            "role_category": "Tactical",
            "role_description": "Researched growth catalyst",
            "rationale": "The researched addition complements the current holdings.",
            "reference_ids": [fixtures.SOURCE_IDS[0]],
        }
    )
    return {
        "portfolio_id": boundaries.PORTFOLIO_ID,
        "summary": "Move toward the validated target with whole-share actions.",
        "positions": positions,
        "data_gaps": [],
    }


def _invoke_review(
    portfolio,
    *,
    country: str,
    investor_theme: str,
    ai,
    rebalance_plan: bool = False,
    prices: dict[str, float | None] | None = None,
    cache: boundaries.MemoryCache | None = None,
    market=None,
):
    memory_cache = cache or boundaries.MemoryCache()
    resolver = market or boundaries.market_resolver(
        prices or _DEFAULT_PRICES,
        company_names=_COMPANY_NAMES,
    )
    with (
        mock.patch.object(service.cache, "get", new=memory_cache.get),
        mock.patch.object(service.cache, "set", new=memory_cache.set),
        mock.patch.object(service.ai_helper, "ai_exec_task", new=ai),
        mock.patch.object(
            service.portfolio_verification.services_stock,
            "resolve_symbol",
            new=resolver,
        ),
    ):
        return asyncio.run(
            service.ai_review_portfolio(
                portfolio,
                country=country,
                investor_theme=investor_theme,
                rebalance_plan=rebalance_plan,
            )
        )


@pytest.mark.parametrize(
    ("theme", "expected"),
    [
        ("Build durable quality exposure", "LongTerm"),
        ("Long-term buy-and-hold growth", "LongTerm"),
        ("Retirement holdings over multiple years", "LongTerm"),
        ("Swing trading over days to weeks", "Swing"),
        ("Short-term trading horizon of 10 days", "Swing"),
        ("", "LongTerm"),
    ],
)
def test_extract_strategy_uses_explicit_cues_and_defaults_to_long_term(theme, expected):
    assert service.extract_strategy(theme) == expected


def test_extract_strategy_rejects_conflicting_explicit_cues():
    with pytest.raises(portfolio_verification.PortfolioInputError):
        service.extract_strategy("Long-term core holdings plus swing trading")


def test_ai_review_portfolio_filters_zero_positions_and_returns_long_term_growth_plan():
    theme = "Long-term growth. Total budget USD 500."
    budget = portfolio_budget.extract_budget(theme, default_currency="USD")
    zero = models_portfolio.PortfolioHolding(
        ticker="NASDAQ:NVDA",
        num_shares=0,
    )
    result = _invoke_review(
        [*fixtures.holdings(), zero],
        country="United States",
        investor_theme=theme,
        ai=_review_ai(budget=budget),
    )

    assert result.result_type == "PortfolioReview"
    assert result.country == "US"
    assert result.strategy == "LongTerm"
    assert {holding.ticker for holding in result.snapshot.holdings} == set(fixtures.TICKERS)
    assert result.budget.budget_type == "Total"
    assert result.budget.amount == 500
    assert result.rebalance_recommended == "NO"
    assert result.action_plan is not None
    assert result.action_plan.plan_type == "Growth"
    assert all(action.action != "TRIM" for action in result.action_plan.actions)
    ledger = result.action_plan.cash_ledger
    assert ledger.new_money_budget + ledger.estimated_sale_proceeds == pytest.approx(
        ledger.purchase_spend + ledger.unallocated_cash
    )
    assert all(action.quantity is None or isinstance(action.quantity, int) for action in result.action_plan.actions)


def test_ai_review_portfolio_repairs_a_retained_lower_target_to_hold_without_sale():
    theme = "Long-term growth. Total budget USD 500."
    budget = portfolio_budget.extract_budget(theme, default_currency="USD")
    target = fixtures.target_data(portfolio_id=boundaries.PORTFOLIO_ID)
    for position, allocation in zip(
        target["positions"],
        [0.45, 0.35, 0.20],
        strict=True,
    ):
        position["allocation"] = allocation

    result = _invoke_review(
        fixtures.holdings(),
        country="US",
        investor_theme=theme,
        ai=_review_ai(
            budget=budget,
            target_data=target,
        ),
    )

    apple_review = next(review for review in result.holding_reviews if review.ticker == "NASDAQ:AAPL")
    assert apple_review.target_allocation < apple_review.current_allocation
    assert apple_review.recommendation == "HOLD"
    assert result.action_plan is not None
    assert all(
        action.action not in {"TRIM", "EXIT"} for action in result.action_plan.actions if action.ticker == "NASDAQ:AAPL"
    )


@pytest.mark.parametrize(
    ("recommendation", "exit_reason"),
    [
        ("TRIM", None),
        ("EXIT", "SwingRiskControl"),
    ],
)
def test_ai_review_portfolio_rejects_unsupported_long_term_sale_intent(
    recommendation,
    exit_reason,
):
    theme = "Long-term growth. Total budget USD 500."
    budget = portfolio_budget.extract_budget(theme, default_currency="USD")
    assessment = fixtures.assessment_data(portfolio_id=boundaries.PORTFOLIO_ID)
    assessment["holding_reviews"][0]["recommendation"] = recommendation
    assessment["holding_reviews"][0]["exit_reason"] = exit_reason

    with pytest.raises(service.PortfolioReviewAIError):
        _invoke_review(
            fixtures.holdings(),
            country="US",
            investor_theme=theme,
            ai=_review_ai(
                budget=budget,
                assessment_data=assessment,
            ),
        )


@pytest.mark.parametrize(
    ("nvda_price", "expected_budget", "expects_purchase"),
    [
        (250, 300, True),
        (400, 200, False),
    ],
)
def test_ai_review_portfolio_uses_bounded_inferred_budget_escalation(
    nvda_price,
    expected_budget,
    expects_purchase,
):
    inferred = portfolio_budget.infer_recurring_budget(
        fixtures.verified_portfolio(),
        rate=Decimal("0.10"),
    )
    result = _invoke_review(
        fixtures.holdings(),
        country="US",
        investor_theme="Long-term durable growth.",
        rebalance_plan=True,
        ai=_review_ai(
            budget=inferred,
            research_data=_research_with_nvda(),
            assessment_data=_assessment_with_nvda(),
            target_data=_target_with_nvda(
                (0.45, 0.27, 0.18, 0.10),
                retain_google=True,
            ),
        ),
        prices={
            **_DEFAULT_PRICES,
            "NASDAQ:NVDA": nvda_price,
        },
    )

    assert result.budget.is_inferred is True
    assert result.budget.amount == expected_budget
    assert result.action_plan is not None
    purchases = [action for action in result.action_plan.actions if action.action in {"BUY_MORE", "INTRODUCE"}]
    assert bool(purchases) is expects_purchase
    if expects_purchase:
        introduced = next(action for action in purchases if action.action == "INTRODUCE")
        assert introduced.quantity == 1
    else:
        assert any(action.action == "ACCUMULATE" for action in result.action_plan.actions)


def test_ai_review_portfolio_recommends_major_rebalance_for_validated_exit():
    theme = "Long-term growth. Total budget USD 500."
    budget = portfolio_budget.extract_budget(theme, default_currency="USD")
    assessment = fixtures.assessment_data(portfolio_id=boundaries.PORTFOLIO_ID)
    assessment["holding_reviews"][2]["recommendation"] = "EXIT"
    assessment["holding_reviews"][2]["exit_reason"] = "StructuralChange"
    target = fixtures.target_data(portfolio_id=boundaries.PORTFOLIO_ID)
    target["positions"] = [
        {**target["positions"][0], "allocation": 0.625},
        {**target["positions"][1], "allocation": 0.375},
    ]
    holdings = fixtures.holdings()
    holding_data = holdings[2].model_dump(mode="python")
    holding_data["num_shares"] = 1
    holdings[2] = models_portfolio.PortfolioHolding.model_validate(holding_data)

    result = _invoke_review(
        holdings,
        country="US",
        investor_theme=theme,
        ai=_review_ai(
            budget=budget,
            assessment_data=assessment,
            target_data=target,
        ),
    )

    assert result.rebalance_recommended == "YES"
    assert result.target_turnover < 0.20
    assert {holding.ticker for holding in result.snapshot.holdings} - {
        position.ticker for position in result.target_portfolio
    } == {"NASDAQ:GOOGL"}
    assert result.major_rebalance_reasons
    assert result.action_plan is None


def test_ai_review_portfolio_recommends_major_rebalance_for_new_holding():
    theme = "Long-term growth. Total budget USD 500."
    budget = portfolio_budget.extract_budget(theme, default_currency="USD")
    result = _invoke_review(
        fixtures.holdings(),
        country="US",
        investor_theme=theme,
        ai=_review_ai(
            budget=budget,
            research_data=_research_with_nvda(),
            assessment_data=_assessment_with_nvda(),
            target_data=_target_with_nvda(
                (0.45, 0.27, 0.18, 0.10),
                retain_google=True,
            ),
        ),
    )

    assert result.rebalance_recommended == "YES"
    assert result.target_turnover < 0.20
    assert {position.ticker for position in result.target_portfolio} - {
        holding.ticker for holding in result.snapshot.holdings
    } == {"NASDAQ:NVDA"}
    assert result.major_rebalance_reasons
    assert result.action_plan is None


def test_ai_review_portfolio_recommends_major_rebalance_at_turnover_threshold():
    theme = "Long-term growth. Total budget USD 500."
    budget = portfolio_budget.extract_budget(theme, default_currency="USD")
    target = fixtures.target_data(portfolio_id=boundaries.PORTFOLIO_ID)
    for position, allocation in zip(
        target["positions"],
        [0.7, 0.2, 0.1],
        strict=True,
    ):
        position["allocation"] = allocation

    result = _invoke_review(
        fixtures.holdings(),
        country="US",
        investor_theme=theme,
        ai=_review_ai(
            budget=budget,
            target_data=target,
        ),
    )

    assert result.rebalance_recommended == "YES"
    assert result.target_turnover == pytest.approx(0.20)
    assert {position.ticker for position in result.target_portfolio} == {
        holding.ticker for holding in result.snapshot.holdings
    }
    assert result.major_rebalance_reasons
    assert result.action_plan is None


def test_ai_review_portfolio_swing_plan_can_exit_trim_buy_and_introduce():
    theme = "Swing trading over days to weeks. Total budget USD 500."
    budget = portfolio_budget.extract_budget(theme, default_currency="USD")
    result = _invoke_review(
        fixtures.holdings(),
        country="US",
        investor_theme=theme,
        rebalance_plan=True,
        ai=_review_ai(
            budget=budget,
            strategy="Swing",
            research_data=_research_with_nvda(),
            assessment_data=_assessment_with_nvda(
                exit_google=True,
                exit_reason="SwingRiskControl",
            ),
            target_data=_target_with_nvda(
                (0.3, 0.3, 0.4),
                retain_google=False,
            ),
        ),
        prices={
            **_DEFAULT_PRICES,
            "NASDAQ:NVDA": 100,
        },
    )

    assert result.strategy == "Swing"
    assert result.rebalance_recommended == "YES"
    assert result.action_plan is not None
    assert {action.action for action in result.action_plan.actions} == {
        "EXIT",
        "TRIM",
        "INTRODUCE",
        "BUY_MORE",
    }
    ledger = result.action_plan.cash_ledger
    assert ledger.new_money_budget + ledger.estimated_sale_proceeds == pytest.approx(
        ledger.purchase_spend + ledger.unallocated_cash
    )


def test_ai_review_portfolio_retains_unmatched_structural_sources_as_unverified():
    theme = "Long-term growth. Total budget USD 500."
    budget = portfolio_budget.extract_budget(theme, default_currency="USD")
    result = _invoke_review(
        fixtures.holdings(),
        country="US",
        investor_theme=theme,
        ai=_review_ai(
            budget=budget,
            citation_urls=(),
        ),
    )

    assert result.references
    assert all(reference.is_verified is False for reference in result.references)
    assert result.review_status == "CompleteWithWarnings"
    assert result.validation_warnings


@pytest.mark.parametrize(
    ("portfolio", "country", "theme"),
    [
        ([], "US", "Long-term growth."),
        (
            [models_portfolio.PortfolioHolding(ticker="NASDAQ:AAPL", num_shares=0)],
            "US",
            "Long-term growth.",
        ),
        (
            [models_portfolio.PortfolioHolding(ticker="NASDAQ:AAPL", num_shares=1.5)],
            "US",
            "Long-term growth.",
        ),
        (fixtures.holdings(), "unknown-market", "Long-term growth."),
        (fixtures.holdings(), "US", "   "),
        (
            fixtures.holdings(),
            "US",
            "Long-term holdings with swing trading.",
        ),
    ],
)
def test_ai_review_portfolio_rejects_invalid_inputs(portfolio, country, theme):
    with pytest.raises(portfolio_verification.PortfolioInputError):
        _invoke_review(
            portfolio,
            country=country,
            investor_theme=theme,
            ai=boundaries.QueuedAI(),
        )


def test_ai_review_portfolio_rejects_budget_currency_mismatch():
    with pytest.raises(portfolio_verification.PortfolioInputError):
        _invoke_review(
            fixtures.holdings(),
            country="US",
            investor_theme="Long-term growth. Total budget AUD 500.",
            ai=boundaries.QueuedAI(),
        )


def test_ai_review_portfolio_reports_addition_price_verification_failure():
    inferred = portfolio_budget.infer_recurring_budget(
        fixtures.verified_portfolio(),
        rate=Decimal("0.10"),
    )
    with pytest.raises(service.PortfolioReviewAIError):
        _invoke_review(
            fixtures.holdings(),
            country="US",
            investor_theme="Long-term durable growth.",
            rebalance_plan=True,
            ai=_review_ai(
                budget=inferred,
                research_data=_research_with_nvda(),
                assessment_data=_assessment_with_nvda(),
                target_data=_target_with_nvda(
                    (0.45, 0.27, 0.18, 0.10),
                    retain_google=True,
                ),
            ),
            prices={
                **_DEFAULT_PRICES,
                "NASDAQ:NVDA": None,
            },
        )


def test_ai_review_portfolio_reports_ai_provider_failure():
    async def rate_limited(*args, **kwargs):
        del args, kwargs
        raise ai_helper.LLMRateLimitError("retry budget exhausted")

    with pytest.raises(service.PortfolioReviewAIError):
        _invoke_review(
            fixtures.holdings(),
            country="US",
            investor_theme="Long-term growth. Total budget USD 500.",
            ai=rate_limited,
        )


def test_ai_review_portfolio_rejects_invalid_structured_ai_output():
    with pytest.raises(service.PortfolioReviewAIError):
        _invoke_review(
            fixtures.holdings(),
            country="US",
            investor_theme="Long-term growth. Total budget USD 500.",
            ai=boundaries.QueuedAI(boundaries.AIResponse({"unexpected": "response"})),
        )


def test_ai_review_portfolio_repeated_calls_return_equal_public_results():
    theme = "Long-term growth. Total budget USD 500."
    budget = portfolio_budget.extract_budget(theme, default_currency="USD")
    cache = boundaries.MemoryCache()
    first = _invoke_review(
        fixtures.holdings(),
        country="US",
        investor_theme=theme,
        ai=_review_ai(budget=budget),
        cache=cache,
    )
    second = _invoke_review(
        fixtures.holdings(),
        country="US",
        investor_theme=theme,
        ai=boundaries.QueuedAI(),
        cache=cache,
        market=boundaries.failing_market,
    )

    assert second == first


def test_ai_review_portfolio_rejects_an_opaque_invalid_cached_result():
    theme = "Long-term growth. Total budget USD 500."
    budget = portfolio_budget.extract_budget(theme, default_currency="USD")
    cache = boundaries.MemoryCache()
    _invoke_review(
        fixtures.holdings(),
        country="US",
        investor_theme=theme,
        ai=_review_ai(budget=budget),
        cache=cache,
    )
    cache.corrupt_latest({"invalid": "cached review"})

    with pytest.raises(RuntimeError):
        _invoke_review(
            fixtures.holdings(),
            country="US",
            investor_theme=theme,
            ai=boundaries.QueuedAI(),
            cache=cache,
            market=boundaries.failing_market,
        )


def test_ai_review_portfolio_refreshes_public_snapshot_after_cache_expiry():
    theme = "Long-term growth. Total budget USD 500."
    budget = portfolio_budget.extract_budget(theme, default_currency="USD")
    cache = boundaries.MemoryCache()
    first = _invoke_review(
        fixtures.holdings(),
        country="US",
        investor_theme=theme,
        ai=_review_ai(budget=budget),
        cache=cache,
    )
    cache.advance(3601)
    second = _invoke_review(
        fixtures.holdings(),
        country="US",
        investor_theme=theme,
        ai=_review_ai(budget=budget),
        prices={
            **_DEFAULT_PRICES,
            "NASDAQ:AAPL": 200,
        },
        cache=cache,
    )

    assert first.snapshot.total_market_value == 2_000
    assert second.snapshot.total_market_value == 3_000
    assert second != first
