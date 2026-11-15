import asyncio
import json
from unittest import mock

import pytest

from app.models import portfolio as models_portfolio
from app.services import ai_helper, portfolio_budget, portfolio_verification
from app.services import msai_review_portfolio as service
from app.services import stock as services_stock
from tests import portfolio_review_fixtures as fixtures


def _resolve_market_symbol(
    ticker: str,
    *,
    nvda_price: float | None = 250,
) -> services_stock.ResolvedSymbol:
    canonical = ticker.strip().upper().replace("NYSEARCA:", "NYSE:")
    exchange, symbol = canonical.split(":", 1)
    prices = {
        "NASDAQ:AAPL": 100,
        "NASDAQ:MSFT": 120,
        "NASDAQ:GOOGL": 100,
        "NASDAQ:NVDA": nvda_price,
    }
    company_names = {
        "NASDAQ:AAPL": "Apple Inc.",
        "NASDAQ:MSFT": "Microsoft Corporation",
        "NASDAQ:GOOGL": "Alphabet Inc.",
        "NASDAQ:NVDA": "NVIDIA Corporation",
    }
    return services_stock.ResolvedSymbol(
        symbol=symbol,
        normalized_symbol=canonical,
        exchange=exchange,
        country="US",
        currency="USD",
        quote_type="EQUITY",
        company_name=company_names[canonical],
        market_price=prices[canonical],
    )


def _action_plan_response(action_ids: list[str]) -> ai_helper.LLMResponse:
    return ai_helper.LLMResponse(
        completion=json.dumps(
            {
                "summary": "Implement the validated target in priority order.",
                "actions": [
                    {
                        "action_id": action_id,
                        "priority": priority,
                        "reasoning": f"{action_id} advances the validated target.",
                    }
                    for priority, action_id in enumerate(action_ids, start=1)
                ],
            }
        )
    )


def _review_responses(
    *,
    theme_budget,
    strategy="LongTerm",
    research_data: dict[str, object] | None = None,
    assessment_data: dict[str, object] | None = None,
    target_data: dict[str, object] | None = None,
    action_ids: list[str] | None = None,
) -> list[ai_helper.LLMResponse]:
    responses = [
        ai_helper.LLMResponse(
            completion=fixtures.plan(
                portfolio_id="portfolio-id",
                budget=theme_budget,
                strategy=strategy,
            ).model_dump_json()
        ),
        ai_helper.LLMResponse(
            completion=json.dumps(research_data or fixtures.research_response_data(portfolio_id="portfolio-id")),
            citation_urls=fixtures.SOURCE_URLS,
        ),
        ai_helper.LLMResponse(
            completion=json.dumps(assessment_data or fixtures.assessment_data(portfolio_id="portfolio-id"))
        ),
        ai_helper.LLMResponse(completion=json.dumps(target_data or fixtures.target_data(portfolio_id="portfolio-id"))),
    ]
    if action_ids is not None:
        responses.append(_action_plan_response(action_ids))
    return responses


def _research_with_nvda() -> dict[str, object]:
    data = fixtures.research_response_data(portfolio_id="portfolio-id")
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
    data = fixtures.assessment_data(portfolio_id="portfolio-id")
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
    current_positions = fixtures.target_data(portfolio_id="portfolio-id")["positions"]
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
        "portfolio_id": "portfolio-id",
        "summary": "Move toward the validated target with whole-share actions.",
        "positions": positions,
        "data_gaps": [],
    }


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
    with pytest.raises(portfolio_verification.PortfolioInputError, match="conflicting"):
        service.extract_strategy("Long-term core holdings plus swing trading")


def test_ai_review_portfolio_filters_zero_positions_and_returns_long_term_growth_plan():
    theme = "Long-term growth. Total budget USD 500."
    budget = portfolio_budget.extract_budget(theme, default_currency="USD")
    zero = models_portfolio.PortfolioHolding(
        ticker="NASDAQ:NVDA",
        num_shares=0,
    )
    responses = _review_responses(
        theme_budget=budget,
        action_ids=[
            "buy_more:NASDAQ:AAPL",
            "buy_more:NASDAQ:GOOGL",
            "hold:NASDAQ:MSFT",
        ],
    )
    with (
        mock.patch.object(service.cache, "generate_hourly_key", return_value="portfolio-id"),
        mock.patch.object(service.cache, "get", new_callable=mock.AsyncMock, return_value=None),
        mock.patch.object(service.cache, "set", new_callable=mock.AsyncMock, return_value=True) as cache_set,
        mock.patch.object(
            service.portfolio_verification.services_stock,
            "resolve_symbol",
            side_effect=_resolve_market_symbol,
        ),
        mock.patch.object(
            service.ai_helper,
            "ai_exec_task",
            new_callable=mock.AsyncMock,
            side_effect=responses,
        ) as ai_exec,
    ):
        result = asyncio.run(
            service.ai_review_portfolio(
                [*fixtures.holdings(), zero],
                country="United States",
                investor_theme=theme,
            )
        )

    assert result.result_type == "PortfolioReview"
    assert result.country == "US"
    assert result.strategy == "LongTerm"
    assert [holding.ticker for holding in result.snapshot.holdings] == sorted(fixtures.TICKERS)
    assert result.rebalance_recommended == "NO"
    assert result.rebalance_requested is False
    assert result.action_plan is not None
    assert result.action_plan.plan_type == "Growth"
    assert [action.action for action in result.action_plan.actions] == [
        "BUY_MORE",
        "BUY_MORE",
        "HOLD",
    ]
    assert not any(action.action == "TRIM" for action in result.action_plan.actions)
    assert result.action_plan.cash_ledger.new_money_budget == 500
    assert result.action_plan.cash_ledger.purchase_spend == 400
    assert result.action_plan.cash_ledger.unallocated_cash == 100
    assert all(action.quantity is None or isinstance(action.quantity, int) for action in result.action_plan.actions)
    assert [call.args[0] for call in ai_exec.await_args_list] == [
        "REVIEW_PORTFOLIO_PLAN",
        "REVIEW_PORTFOLIO_RESEARCH",
        "REVIEW_PORTFOLIO_ASSESS",
        "REVIEW_PORTFOLIO_TARGET",
        "REVIEW_PORTFOLIO_ACTION_PLAN",
    ]
    assert any(call.kwargs["ttl"] == 60 * 60 for call in cache_set.await_args_list)


@pytest.mark.parametrize("rebalance_plan", [False, True])
def test_ai_review_portfolio_obeys_major_rebalance_request_semantics(rebalance_plan):
    theme = "Long-term growth. Total budget USD 500."
    budget = portfolio_budget.extract_budget(theme, default_currency="USD")
    assessment = fixtures.assessment_data(portfolio_id="portfolio-id")
    assessment["holding_reviews"][2]["recommendation"] = "EXIT"
    assessment["holding_reviews"][2]["exit_reason"] = "CriticalRisk"
    target = fixtures.target_data(portfolio_id="portfolio-id")
    target["positions"] = [
        {
            **target["positions"][0],
            "allocation": 0.6,
        },
        {
            **target["positions"][1],
            "allocation": 0.4,
        },
    ]
    action_ids = (
        [
            "exit:NASDAQ:GOOGL",
            "buy_more:NASDAQ:AAPL",
            "buy_more:NASDAQ:MSFT",
        ]
        if rebalance_plan
        else None
    )
    with (
        mock.patch.object(service.cache, "generate_hourly_key", return_value="portfolio-id"),
        mock.patch.object(service.cache, "get", new_callable=mock.AsyncMock, return_value=None),
        mock.patch.object(service.cache, "set", new_callable=mock.AsyncMock, return_value=True),
        mock.patch.object(
            service.portfolio_verification.services_stock,
            "resolve_symbol",
            side_effect=_resolve_market_symbol,
        ),
        mock.patch.object(
            service.ai_helper,
            "ai_exec_task",
            new_callable=mock.AsyncMock,
            side_effect=_review_responses(
                theme_budget=budget,
                assessment_data=assessment,
                target_data=target,
                action_ids=action_ids,
            ),
        ),
    ):
        result = asyncio.run(
            service.ai_review_portfolio(
                fixtures.holdings(),
                country="US",
                investor_theme=theme,
                rebalance_plan=rebalance_plan,
            )
        )

    assert result.rebalance_recommended == "YES"
    assert result.rebalance_requested is rebalance_plan
    assert result.target_turnover == pytest.approx(0.2)
    assert result.major_rebalance_reasons
    if rebalance_plan:
        assert result.action_plan is not None
        assert result.action_plan.plan_type == "Rebalance"
        assert [action.action for action in result.action_plan.actions] == [
            "EXIT",
            "BUY_MORE",
            "BUY_MORE",
        ]
        assert result.action_plan.cash_ledger.estimated_sale_proceeds == 400
    else:
        assert result.action_plan is None


def test_ai_review_portfolio_increases_inferred_budget_only_when_it_enables_a_whole_share():
    inferred = portfolio_budget.infer_recurring_budget(
        fixtures.verified_portfolio(),
        rate=portfolio_budget.INFERRED_BUDGET_MIN_RATE,
    )
    with (
        mock.patch.object(service.cache, "generate_hourly_key", return_value="portfolio-id"),
        mock.patch.object(service.cache, "get", new_callable=mock.AsyncMock, return_value=None),
        mock.patch.object(service.cache, "set", new_callable=mock.AsyncMock, return_value=True),
        mock.patch.object(
            service.portfolio_verification.services_stock,
            "resolve_symbol",
            side_effect=_resolve_market_symbol,
        ),
        mock.patch.object(
            service.ai_helper,
            "ai_exec_task",
            new_callable=mock.AsyncMock,
            side_effect=_review_responses(
                theme_budget=inferred,
                research_data=_research_with_nvda(),
                assessment_data=_assessment_with_nvda(),
                target_data=_target_with_nvda(
                    (0.45, 0.27, 0.18, 0.10),
                    retain_google=True,
                ),
                action_ids=[
                    "introduce:NASDAQ:NVDA",
                    "hold:NASDAQ:AAPL",
                    "hold:NASDAQ:MSFT",
                    "hold:NASDAQ:GOOGL",
                ],
            ),
        ),
    ):
        result = asyncio.run(
            service.ai_review_portfolio(
                fixtures.holdings(),
                country="US",
                investor_theme="Long-term durable growth.",
                rebalance_plan=True,
            )
        )

    assert result.budget.is_inferred is True
    assert result.budget.amount == 300
    assert "15%" in result.budget.source_text
    assert result.action_plan is not None
    introduced = next(action for action in result.action_plan.actions if action.action == "INTRODUCE")
    assert introduced.ticker == "NASDAQ:NVDA"
    assert introduced.quantity == 1
    assert result.action_plan.cash_ledger.purchase_spend == 250
    assert result.action_plan.cash_ledger.unallocated_cash == 50


def test_ai_review_portfolio_swing_plan_can_exit_trim_buy_and_introduce():
    theme = "Swing trading over days to weeks. Total budget USD 500."
    budget = portfolio_budget.extract_budget(theme, default_currency="USD")
    with (
        mock.patch.object(service.cache, "generate_hourly_key", return_value="portfolio-id"),
        mock.patch.object(service.cache, "get", new_callable=mock.AsyncMock, return_value=None),
        mock.patch.object(service.cache, "set", new_callable=mock.AsyncMock, return_value=True),
        mock.patch.object(
            service.portfolio_verification.services_stock,
            "resolve_symbol",
            side_effect=lambda ticker: _resolve_market_symbol(ticker, nvda_price=100),
        ),
        mock.patch.object(
            service.ai_helper,
            "ai_exec_task",
            new_callable=mock.AsyncMock,
            side_effect=_review_responses(
                theme_budget=budget,
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
                action_ids=[
                    "exit:NASDAQ:GOOGL",
                    "trim:NASDAQ:AAPL",
                    "introduce:NASDAQ:NVDA",
                    "buy_more:NASDAQ:MSFT",
                ],
            ),
        ),
    ):
        result = asyncio.run(
            service.ai_review_portfolio(
                fixtures.holdings(),
                country="US",
                investor_theme=theme,
                rebalance_plan=True,
            )
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
    assert ledger.estimated_sale_proceeds == 600
    assert ledger.new_money_budget + ledger.estimated_sale_proceeds == (ledger.purchase_spend + ledger.unallocated_cash)


@pytest.mark.parametrize(
    ("portfolio", "country", "theme", "message"),
    [
        ([], "US", "Long-term growth.", "positive-share position"),
        (
            [models_portfolio.PortfolioHolding(ticker="NASDAQ:AAPL", num_shares=0)],
            "US",
            "Long-term growth.",
            "positive-share position",
        ),
        (
            [models_portfolio.PortfolioHolding(ticker="NASDAQ:AAPL", num_shares=1.5)],
            "US",
            "Long-term growth.",
            "whole-share",
        ),
        (fixtures.holdings(), "unknown-market", "Long-term growth.", "Unsupported or unknown country"),
        (fixtures.holdings(), "US", "   ", "Investor theme must not be empty"),
        (
            fixtures.holdings(),
            "US",
            "Long-term holdings with swing trading.",
            "conflicting",
        ),
    ],
)
def test_ai_review_portfolio_rejects_invalid_inputs_before_ai(
    portfolio,
    country,
    theme,
    message,
):
    with (
        mock.patch.object(service.ai_helper, "ai_exec_task", new_callable=mock.AsyncMock) as ai_exec,
        mock.patch.object(
            service.portfolio_verification.services_stock,
            "resolve_symbol",
        ) as resolve_symbol,
        pytest.raises(portfolio_verification.PortfolioInputError, match=message),
    ):
        asyncio.run(
            service.ai_review_portfolio(
                portfolio,
                country=country,
                investor_theme=theme,
            )
        )

    ai_exec.assert_not_awaited()
    resolve_symbol.assert_not_called()


def test_ai_review_portfolio_rejects_budget_currency_mismatch_before_ai():
    with (
        mock.patch.object(service.cache, "get", new_callable=mock.AsyncMock, return_value=None),
        mock.patch.object(service.cache, "set", new_callable=mock.AsyncMock, return_value=True),
        mock.patch.object(
            service.portfolio_verification.services_stock,
            "resolve_symbol",
            side_effect=_resolve_market_symbol,
        ),
        mock.patch.object(service.ai_helper, "ai_exec_task", new_callable=mock.AsyncMock) as ai_exec,
        pytest.raises(portfolio_verification.PortfolioInputError, match="portfolio currency"),
    ):
        asyncio.run(
            service.ai_review_portfolio(
                fixtures.holdings(),
                country="US",
                investor_theme="Long-term growth. Total budget AUD 500.",
            )
        )

    ai_exec.assert_not_awaited()


def test_ai_review_portfolio_wraps_addition_price_verification_failure():
    inferred = portfolio_budget.infer_recurring_budget(
        fixtures.verified_portfolio(),
        rate=portfolio_budget.INFERRED_BUDGET_MIN_RATE,
    )
    with (
        mock.patch.object(service.cache, "generate_hourly_key", return_value="portfolio-id"),
        mock.patch.object(service.cache, "get", new_callable=mock.AsyncMock, return_value=None),
        mock.patch.object(service.cache, "set", new_callable=mock.AsyncMock, return_value=True),
        mock.patch.object(
            service.portfolio_verification.services_stock,
            "resolve_symbol",
            side_effect=lambda ticker: _resolve_market_symbol(ticker, nvda_price=None),
        ),
        mock.patch.object(
            service.ai_helper,
            "ai_exec_task",
            new_callable=mock.AsyncMock,
            side_effect=_review_responses(
                theme_budget=inferred,
                research_data=_research_with_nvda(),
                assessment_data=_assessment_with_nvda(),
                target_data=_target_with_nvda(
                    (0.45, 0.27, 0.18, 0.10),
                    retain_google=True,
                ),
            ),
        ),
        pytest.raises(service.PortfolioReviewAIError, match="target-price verification failed"),
    ):
        asyncio.run(
            service.ai_review_portfolio(
                fixtures.holdings(),
                country="US",
                investor_theme="Long-term durable growth.",
                rebalance_plan=True,
            )
        )


def test_ai_review_portfolio_wraps_exhausted_rate_limit_as_service_error():
    with (
        mock.patch.object(service.cache, "generate_hourly_key", return_value="portfolio-id"),
        mock.patch.object(service.cache, "get", new_callable=mock.AsyncMock, return_value=None),
        mock.patch.object(service.cache, "set", new_callable=mock.AsyncMock, return_value=True),
        mock.patch.object(
            service.portfolio_verification.services_stock,
            "resolve_symbol",
            side_effect=_resolve_market_symbol,
        ),
        mock.patch.object(
            service.ai_helper,
            "ai_exec_task",
            new_callable=mock.AsyncMock,
            side_effect=ai_helper.LLMRateLimitError("retry budget exhausted"),
        ),
        pytest.raises(service.PortfolioReviewAIError, match="planning provider failed"),
    ):
        asyncio.run(
            service.ai_review_portfolio(
                fixtures.holdings(),
                country="US",
                investor_theme="Long-term growth. Total budget USD 500.",
            )
        )


def test_ai_review_portfolio_returns_validated_final_cache_before_action_stage():
    expected = fixtures.review()
    cached_values = [
        None,
        fixtures.plan(portfolio_id="portfolio-id").model_dump(mode="json"),
        fixtures.research(portfolio_id="portfolio-id").model_dump(mode="json"),
        fixtures.assessment(portfolio_id="portfolio-id").model_dump(mode="json"),
        fixtures.target(portfolio_id="portfolio-id").model_dump(mode="json"),
        expected.model_dump(mode="json"),
    ]
    with (
        mock.patch.object(service.cache, "generate_hourly_key", return_value="portfolio-id"),
        mock.patch.object(
            service.cache,
            "get",
            new_callable=mock.AsyncMock,
            side_effect=cached_values,
        ),
        mock.patch.object(service.cache, "set", new_callable=mock.AsyncMock),
        mock.patch.object(
            service.portfolio_verification.services_stock,
            "resolve_symbol",
            side_effect=_resolve_market_symbol,
        ),
        mock.patch.object(service.ai_helper, "ai_exec_task", new_callable=mock.AsyncMock) as ai_exec,
    ):
        result = asyncio.run(
            service.ai_review_portfolio(
                fixtures.holdings(),
                country="US",
                investor_theme="Long-term growth. Total budget USD 500.",
            )
        )

    assert result == expected
    ai_exec.assert_not_awaited()


def test_ai_review_portfolio_rejects_invalid_cached_stage():
    with (
        mock.patch.object(service.cache, "generate_hourly_key", return_value="portfolio-id"),
        mock.patch.object(
            service.cache,
            "get",
            new_callable=mock.AsyncMock,
            side_effect=[None, {"unexpected": "value"}],
        ),
        mock.patch.object(service.cache, "set", new_callable=mock.AsyncMock),
        mock.patch.object(
            service.portfolio_verification.services_stock,
            "resolve_symbol",
            side_effect=_resolve_market_symbol,
        ),
        mock.patch.object(service.ai_helper, "ai_exec_task", new_callable=mock.AsyncMock) as ai_exec,
        pytest.raises(RuntimeError, match="planning cache contains an invalid value"),
    ):
        asyncio.run(
            service.ai_review_portfolio(
                fixtures.holdings(),
                country="US",
                investor_theme="Long-term growth. Total budget USD 500.",
            )
        )

    ai_exec.assert_not_awaited()
