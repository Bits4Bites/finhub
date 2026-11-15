import asyncio
import decimal
import json
from unittest import mock

import pytest

from app.services import ai_helper, portfolio_budget, portfolio_verification
from app.services import msai_build_portfolio as service
from app.services import stock as services_stock
from tests import portfolio_construction_fixtures as fixtures


def _resolve_market_symbol(ticker: str) -> services_stock.ResolvedSymbol:
    canonical = ticker.strip().upper().replace("NYSEARCA:", "NYSE:")
    exchange, symbol = canonical.split(":", 1)
    prices = {
        "NASDAQ:AAPL": 200,
        "NASDAQ:MSFT": 400,
        "NASDAQ:GOOGL": 160,
    }
    company_names = {
        "NASDAQ:AAPL": "Apple Inc.",
        "NASDAQ:MSFT": "Microsoft Corporation",
        "NASDAQ:GOOGL": "Alphabet Inc.",
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


def _construction_responses(
    *,
    budget,
    mode="Scratch",
    action_ids: list[str] | None = None,
) -> list[ai_helper.LLMResponse]:
    responses = [
        ai_helper.LLMResponse(completion=fixtures.plan(mode, budget=budget).model_dump_json()),
        ai_helper.LLMResponse(
            completion=json.dumps(fixtures.research_response_data()),
            citation_urls=[fixtures.SOURCE_URL],
        ),
        ai_helper.LLMResponse(completion=json.dumps(fixtures.draft_data())),
    ]
    if action_ids is not None:
        responses.append(
            ai_helper.LLMResponse(
                completion=fixtures.action_plan_draft(action_ids).model_dump_json(),
            )
        )
    return responses


@pytest.mark.parametrize(
    ("theme", "default_currency", "expected"),
    [
        (
            "Build a diversified portfolio with a total budget of USD 10,000.",
            "AUD",
            ("Total", 10_000, "USD", None),
        ),
        (
            "Invest a recurring $500 per month for retirement.",
            "USD",
            ("Recurring", 500, "USD", "Monthly"),
        ),
        (
            "Contribute 250 EUR every two weeks.",
            "USD",
            ("Recurring", 250, "EUR", "Fortnightly"),
        ),
        ("Invest 2.5k USD.", "AUD", ("Total", 2_500, "USD", None)),
        ("Use 1 234.50 EUR as the total budget.", "USD", ("Total", 1_234.50, "EUR", None)),
        ("Invest 500.", "eur", ("Total", 500, "EUR", None)),
        ("Invest $500.", "aud", ("Total", 500, "AUD", None)),
        ("Invest ¥500.", "cny", ("Total", 500, "CNY", None)),
        (
            "Build a diversified portfolio of stocks priced under $20 per share.",
            "USD",
            ("NotProvided", None, None, None),
        ),
        (
            "Build a durable growth portfolio.",
            "USD",
            ("NotProvided", None, None, None),
        ),
    ],
)
def test_extract_budget_returns_the_documented_budget_contract(
    theme,
    default_currency,
    expected,
):
    result = portfolio_budget.extract_budget(
        theme,
        default_currency=default_currency,
    )

    assert (result.budget_type, result.amount, result.currency, result.frequency) == expected
    assert result.is_inferred is False
    if result.budget_type == "NotProvided":
        assert result.source_text is None
    else:
        assert result.source_text


@pytest.mark.parametrize(
    ("theme", "default_currency", "message"),
    [
        ("Use a USD 10,000 total budget plus USD 500 monthly.", "USD", "multiple"),
        ("Invest a recurring USD 500.", "USD", "must include"),
        ("Use an investment budget of -$500.", "USD", "positive"),
        ("Use an investment budget of USD 0.", "USD", "positive"),
        ("Invest 500.", "", "currency could not be inferred"),
    ],
)
def test_extract_budget_rejects_ambiguous_or_invalid_budget_expressions(
    theme,
    default_currency,
    message,
):
    with pytest.raises(portfolio_verification.PortfolioInputError, match=message):
        portfolio_budget.extract_budget(
            theme,
            default_currency=default_currency,
        )


def test_extract_budget_preserves_recurring_frequency_context_and_handles_long_non_budget_numbers():
    recurring = portfolio_budget.extract_budget(
        "Prefer diversification. Invest a recurring $500 per month for retirement.",
        default_currency="USD",
    )
    no_budget = portfolio_budget.extract_budget(
        "1" * 3_999 + "!",
        default_currency="USD",
    )

    assert recurring.source_text == "Invest a recurring $500 per month for retirement"
    assert no_budget.budget_type == "NotProvided"


def test_infer_recurring_budget_uses_positive_rate_and_six_decimal_money():
    result = portfolio_budget.infer_recurring_budget(
        fixtures.verified_portfolio(),
        rate=decimal.Decimal("0.123456789"),
    )

    assert result.budget_type == "Recurring"
    assert result.is_inferred is True
    assert result.amount == 246.913578
    assert result.currency == "USD"
    assert result.frequency is None
    assert "12%" in result.source_text


@pytest.mark.parametrize("rate", [decimal.Decimal("0"), decimal.Decimal("-0.1"), decimal.Decimal("NaN")])
def test_infer_recurring_budget_rejects_non_positive_or_non_finite_rates(rate):
    with pytest.raises(portfolio_verification.PortfolioInputError, match="rate"):
        portfolio_budget.infer_recurring_budget(
            fixtures.verified_portfolio(),
            rate=rate,
        )


def test_infer_recurring_budget_rejects_positive_contribution_that_rounds_to_zero():
    with pytest.raises(portfolio_verification.PortfolioInputError, match="too small"):
        portfolio_budget.infer_recurring_budget(
            fixtures.verified_portfolio(),
            rate=decimal.Decimal("0.0000000001"),
        )


def test_allocate_whole_shares_returns_deterministic_quantities_and_exact_utilized_budget():
    quantities, utilized = portfolio_budget.allocate_whole_shares(
        decimal.Decimal("1000"),
        desired_amounts={
            "NASDAQ:AAPL": decimal.Decimal("400"),
            "NASDAQ:MSFT": decimal.Decimal("350"),
            "NASDAQ:GOOGL": decimal.Decimal("250"),
        },
        prices={
            "NASDAQ:AAPL": decimal.Decimal("200"),
            "NASDAQ:MSFT": decimal.Decimal("400"),
            "NASDAQ:GOOGL": decimal.Decimal("160"),
        },
    )

    assert quantities == {
        "NASDAQ:AAPL": 2,
        "NASDAQ:MSFT": 1,
        "NASDAQ:GOOGL": 1,
    }
    assert all(isinstance(quantity, int) and quantity >= 0 for quantity in quantities.values())
    assert utilized == decimal.Decimal("960")
    assert utilized == sum(
        (
            decimal.Decimal(quantities[ticker]) * price
            for ticker, price in {
                "NASDAQ:AAPL": decimal.Decimal("200"),
                "NASDAQ:MSFT": decimal.Decimal("400"),
                "NASDAQ:GOOGL": decimal.Decimal("160"),
            }.items()
        ),
        decimal.Decimal("0"),
    )
    assert utilized <= decimal.Decimal("1000")


@pytest.mark.parametrize(
    ("budget", "desired", "prices", "message"),
    [
        (
            decimal.Decimal("0"),
            {"NASDAQ:AAPL": decimal.Decimal("100")},
            {"NASDAQ:AAPL": decimal.Decimal("100")},
            "budget",
        ),
        (
            decimal.Decimal("100"),
            {},
            {},
            "at least one",
        ),
        (
            decimal.Decimal("100"),
            {"NASDAQ:AAPL": decimal.Decimal("100")},
            {"NASDAQ:MSFT": decimal.Decimal("100")},
            "same tickers",
        ),
        (
            decimal.Decimal("100"),
            {"NASDAQ:AAPL": decimal.Decimal("-1")},
            {"NASDAQ:AAPL": decimal.Decimal("100")},
            "desired amounts",
        ),
        (
            decimal.Decimal("100"),
            {"NASDAQ:AAPL": decimal.Decimal("100")},
            {"NASDAQ:AAPL": decimal.Decimal("0")},
            "prices",
        ),
    ],
)
def test_allocate_whole_shares_rejects_invalid_values(
    budget,
    desired,
    prices,
    message,
):
    with pytest.raises(ValueError, match=message):
        portfolio_budget.allocate_whole_shares(
            budget,
            desired_amounts=desired,
            prices=prices,
        )


def test_allocate_whole_shares_rejects_initial_whole_share_cost_above_budget():
    with pytest.raises(ValueError, match="exceeded"):
        portfolio_budget.allocate_whole_shares(
            decimal.Decimal("100"),
            desired_amounts={
                "NASDAQ:AAPL": decimal.Decimal("100"),
                "NASDAQ:MSFT": decimal.Decimal("100"),
            },
            prices={
                "NASDAQ:AAPL": decimal.Decimal("60"),
                "NASDAQ:MSFT": decimal.Decimal("60"),
            },
        )


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        (decimal.Decimal("1.2345675"), 1.234568),
        (decimal.Decimal("1.2345665"), 1.234566),
        (decimal.Decimal("-2.0000006"), -2.000001),
        (decimal.Decimal("0"), 0.0),
    ],
)
def test_round_money_rounds_to_six_decimal_places(amount, expected):
    assert portfolio_budget.round_money(amount) == expected


def test_round_money_rejects_non_finite_values():
    with pytest.raises(ValueError, match="finite"):
        portfolio_budget.round_money(decimal.Decimal("Infinity"))


def test_ai_build_portfolio_filters_zero_positions_and_returns_scratch_target_without_budget():
    responses = _construction_responses(
        budget=fixtures.no_budget(),
    )
    with (
        mock.patch.object(service.cache, "get", new_callable=mock.AsyncMock, return_value=None),
        mock.patch.object(service.cache, "set", new_callable=mock.AsyncMock, return_value=True) as cache_set,
        mock.patch.object(
            service.portfolio_verification.services_stock,
            "resolve_symbol",
            side_effect=_resolve_market_symbol,
        ) as resolve_symbol,
        mock.patch.object(
            service.ai_helper,
            "ai_exec_task",
            new_callable=mock.AsyncMock,
            side_effect=responses,
        ) as ai_exec,
    ):
        result = asyncio.run(
            service.ai_build_portfolio(
                [fixtures.holding(num_shares=0)],
                country="United States",
                investor_theme="Durable growth with moderate risk.",
            )
        )

    assert result.construction_mode == "Scratch"
    assert result.country == "US"
    assert result.verified_seed_holdings == []
    assert sum(position.allocation for position in result.target_portfolio) == pytest.approx(1)
    assert result.action_plan is None
    assert "action plan cannot be built" in result.data_gaps[0]
    assert all(reference.is_verified for reference in result.references)
    assert [call.args[0] for call in ai_exec.await_args_list] == [
        "BUILD_PORTFOLIO_PLAN",
        "BUILD_PORTFOLIO_RESEARCH",
        "BUILD_PORTFOLIO_CONSTRUCT",
    ]
    assert resolve_symbol.call_count == 3
    assert all(call.kwargs["ttl"] == 60 * 60 for call in cache_set.await_args_list)


def test_ai_build_portfolio_returns_budget_reconciled_whole_share_action_plan():
    theme = "Build a durable growth portfolio with a total budget of USD 1,000."
    budget = portfolio_budget.extract_budget(theme, default_currency="USD")
    responses = _construction_responses(
        budget=budget,
        action_ids=[
            "buy:NASDAQ:AAPL",
            "buy:NASDAQ:MSFT",
            "buy:NASDAQ:GOOGL",
        ],
    )
    with (
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
            side_effect=responses,
        ),
    ):
        result = asyncio.run(
            service.ai_build_portfolio(
                [],
                country="US",
                investor_theme=theme,
            )
        )

    assert result.action_plan is not None
    assert result.action_plan.budget == budget
    assert result.action_plan.budget_utilized == 960
    assert result.action_plan.unallocated_amount == 40
    assert result.action_plan.budget_utilized + result.action_plan.unallocated_amount == budget.amount
    assert [step.quantity for step in result.action_plan.steps] == [2, 1, 1]
    assert all(step.quantity is None or isinstance(step.quantity, int) for step in result.action_plan.steps)


def test_ai_build_portfolio_verifies_only_positive_seed_positions_and_infers_budget():
    positive = fixtures.holding()
    zero = fixtures.holding("NASDAQ:MSFT", num_shares=0)
    inferred = fixtures.inferred_budget()
    responses = _construction_responses(
        budget=inferred,
        mode="Seeded",
        action_ids=[
            "buy:NASDAQ:GOOGL",
            "accumulate:NASDAQ:MSFT",
            "hold:NASDAQ:AAPL",
        ],
    )
    with (
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
            side_effect=responses,
        ),
    ):
        result = asyncio.run(
            service.ai_build_portfolio(
                [zero, positive],
                country="US",
                investor_theme="Durable growth with moderate risk.",
            )
        )

    assert result.construction_mode == "Seeded"
    assert [holding.ticker for holding in result.verified_seed_holdings] == ["NASDAQ:AAPL"]
    assert result.action_plan is not None
    assert result.action_plan.budget.is_inferred is True
    assert result.action_plan.budget.amount == 200
    assert all(step.action != "TRIM" for step in result.action_plan.steps)


@pytest.mark.parametrize(
    ("portfolio", "country", "theme", "message"),
    [
        ([], "unknown-market", "Durable growth.", "Unsupported or unknown country"),
        ([], "US", "   ", "Investor theme must not be empty"),
        ([fixtures.holding(num_shares=1.5)], "US", "Durable growth.", "whole-share"),
    ],
)
def test_ai_build_portfolio_rejects_invalid_inputs_before_ai(
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
            service.ai_build_portfolio(
                portfolio,
                country=country,
                investor_theme=theme,
            )
        )

    ai_exec.assert_not_awaited()
    resolve_symbol.assert_not_called()


def test_ai_build_portfolio_rejects_budget_currency_that_differs_from_seed_holdings():
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
            service.ai_build_portfolio(
                [fixtures.holding()],
                country="US",
                investor_theme="Build a durable portfolio with an AUD 1,000 total budget.",
            )
        )

    ai_exec.assert_not_awaited()


def test_ai_build_portfolio_wraps_target_price_verification_failure():
    theme = "Build a durable growth portfolio with a total budget of USD 1,000."
    budget = portfolio_budget.extract_budget(theme, default_currency="USD")
    call_counts: dict[str, int] = {}

    def resolve_with_missing_quote(ticker: str) -> services_stock.ResolvedSymbol:
        resolved = _resolve_market_symbol(ticker)
        call_counts[ticker] = call_counts.get(ticker, 0) + 1
        if ticker == "NASDAQ:MSFT" and call_counts[ticker] > 1:
            return services_stock.ResolvedSymbol(
                **{**resolved.__dict__, "market_price": None},
            )
        return resolved

    with (
        mock.patch.object(service.cache, "get", new_callable=mock.AsyncMock, return_value=None),
        mock.patch.object(service.cache, "set", new_callable=mock.AsyncMock, return_value=True),
        mock.patch.object(
            service.portfolio_verification.services_stock,
            "resolve_symbol",
            side_effect=resolve_with_missing_quote,
        ),
        mock.patch.object(
            service.ai_helper,
            "ai_exec_task",
            new_callable=mock.AsyncMock,
            side_effect=_construction_responses(budget=budget),
        ),
        pytest.raises(service.PortfolioConstructionAIError, match="target-price verification failed"),
    ):
        asyncio.run(
            service.ai_build_portfolio(
                [],
                country="US",
                investor_theme=theme,
            )
        )


def test_ai_build_portfolio_wraps_exhausted_rate_limit_as_service_error():
    with (
        mock.patch.object(service.cache, "get", new_callable=mock.AsyncMock, return_value=None),
        mock.patch.object(
            service.ai_helper,
            "ai_exec_task",
            new_callable=mock.AsyncMock,
            side_effect=ai_helper.LLMRateLimitError("retry budget exhausted"),
        ),
        pytest.raises(service.PortfolioConstructionAIError, match="planning provider failed"),
    ):
        asyncio.run(
            service.ai_build_portfolio(
                [],
                country="US",
                investor_theme="Durable growth with moderate risk.",
            )
        )


def test_ai_build_portfolio_reuses_validated_stage_and_final_caches():
    expected = fixtures.construction(action_plan_available=False)
    cached_values = [
        fixtures.plan().model_dump(mode="json"),
        fixtures.research().model_dump(mode="json"),
        fixtures.draft_data(),
        expected.model_dump(mode="json"),
    ]
    with (
        mock.patch.object(
            service.cache,
            "get",
            new_callable=mock.AsyncMock,
            side_effect=cached_values,
        ),
        mock.patch.object(service.cache, "set", new_callable=mock.AsyncMock) as cache_set,
        mock.patch.object(service.ai_helper, "ai_exec_task", new_callable=mock.AsyncMock) as ai_exec,
        mock.patch.object(
            service.portfolio_verification.services_stock,
            "resolve_symbol",
        ) as resolve_symbol,
    ):
        result = asyncio.run(
            service.ai_build_portfolio(
                [],
                country="US",
                investor_theme="Durable growth with moderate risk.",
            )
        )

    assert result == expected
    ai_exec.assert_not_awaited()
    resolve_symbol.assert_not_called()
    cache_set.assert_not_awaited()


def test_ai_build_portfolio_rejects_invalid_cached_stage():
    with (
        mock.patch.object(
            service.cache,
            "get",
            new_callable=mock.AsyncMock,
            return_value={"unexpected": "value"},
        ),
        mock.patch.object(service.ai_helper, "ai_exec_task", new_callable=mock.AsyncMock) as ai_exec,
        pytest.raises(RuntimeError, match="planning cache contains an invalid value"),
    ):
        asyncio.run(
            service.ai_build_portfolio(
                [],
                country="US",
                investor_theme="Durable growth with moderate risk.",
            )
        )

    ai_exec.assert_not_awaited()
