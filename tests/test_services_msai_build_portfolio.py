import asyncio
import decimal
from unittest import mock

import pytest

from app.services import ai_helper, portfolio_budget, portfolio_verification
from app.services import msai_build_portfolio as service
from tests import portfolio_construction_fixtures as fixtures
from tests import portfolio_service_fixtures as boundaries

_DEFAULT_PRICES = {
    "NASDAQ:AAPL": 200,
    "NASDAQ:MSFT": 400,
    "NASDAQ:GOOGL": 160,
}
_COMPANY_NAMES = {
    "NASDAQ:AAPL": "Apple Inc.",
    "NASDAQ:MSFT": "Microsoft Corporation",
    "NASDAQ:GOOGL": "Alphabet Inc.",
}


def _construction_ai(
    *,
    budget,
    mode="Scratch",
    draft_data: dict[str, object] | None = None,
    citation_urls: tuple[str, ...] = (fixtures.SOURCE_URL,),
) -> boundaries.QueuedAI:
    return boundaries.QueuedAI(
        boundaries.AIResponse(fixtures.plan_data(mode, budget=budget)),
        boundaries.AIResponse(
            fixtures.research_response_data(),
            citation_urls=citation_urls,
        ),
        boundaries.AIResponse(draft_data or fixtures.draft_data()),
        boundaries.AIResponse(
            {
                "summary": "Implement the validated actions in priority order.",
                "steps": boundaries.ACTION_REASONING,
            }
        ),
    )


def _invoke_build(
    portfolio,
    *,
    country: str,
    investor_theme: str,
    ai,
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
            service.ai_build_portfolio(
                portfolio,
                country=country,
                investor_theme=investor_theme,
            )
        )


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
        (
            "Contribute USD 100 each week.",
            "USD",
            ("Recurring", 100, "USD", "Weekly"),
        ),
        (
            "Make a regular GBP 300 contribution per quarter.",
            "USD",
            ("Recurring", 300, "GBP", "Quarterly"),
        ),
        (
            "Invest a recurring JPY 50,000 annually.",
            "USD",
            ("Recurring", 50_000, "JPY", "Annually"),
        ),
        ("Invest 2.5k USD.", "AUD", ("Total", 2_500, "USD", None)),
        ("Invest $500.", "AUD", ("Total", 500, "AUD", None)),
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
def test_extract_budget_returns_total_recurring_or_absent_budget(
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
    assert (result.source_text is None) is (result.budget_type == "NotProvided")


@pytest.mark.parametrize(
    "currency",
    [
        "AUD",
        "CAD",
        "CHF",
        "CNY",
        "EUR",
        "GBP",
        "HKD",
        "INR",
        "JPY",
        "NZD",
        "SGD",
        "USD",
        "VND",
    ],
)
def test_extract_budget_supports_documented_currency_codes(currency):
    result = portfolio_budget.extract_budget(
        f"Use a total budget of {currency} 125.",
        default_currency="USD",
    )

    assert result.amount == 125
    assert result.currency == currency


@pytest.mark.parametrize(
    ("marker", "default_currency", "expected_currency"),
    [
        ("€", "USD", "EUR"),
        ("£", "USD", "GBP"),
        ("A$", "USD", "AUD"),
        ("$", "CAD", "CAD"),
        ("$", "EUR", "USD"),
        ("¥", "CNY", "CNY"),
        ("¥", "USD", "JPY"),
    ],
)
def test_extract_budget_resolves_documented_currency_symbols(
    marker,
    default_currency,
    expected_currency,
):
    result = portfolio_budget.extract_budget(
        f"Invest a total budget of {marker}500.",
        default_currency=default_currency,
    )

    assert result.currency == expected_currency


@pytest.mark.parametrize(
    ("theme", "default_currency"),
    [
        ("Use a USD 10,000 total budget plus USD 500 monthly.", "USD"),
        ("Invest a recurring USD 500.", "USD"),
        ("Use an investment budget of -$500.", "USD"),
        ("Use an investment budget of USD 0.", "USD"),
        ("Invest 500.", ""),
    ],
)
def test_extract_budget_rejects_ambiguous_or_invalid_budget_expressions(
    theme,
    default_currency,
):
    with pytest.raises(portfolio_verification.PortfolioInputError):
        portfolio_budget.extract_budget(
            theme,
            default_currency=default_currency,
        )


def test_infer_recurring_budget_uses_verified_value_without_inventing_frequency():
    result = portfolio_budget.infer_recurring_budget(
        fixtures.verified_portfolio(),
        rate=decimal.Decimal("0.123456789"),
    )

    assert result.budget_type == "Recurring"
    assert result.is_inferred is True
    assert result.amount == 246.913578
    assert result.currency == "USD"
    assert result.frequency is None
    assert result.source_text


@pytest.mark.parametrize(
    "rate",
    [
        decimal.Decimal("0"),
        decimal.Decimal("-0.1"),
        decimal.Decimal("NaN"),
        decimal.Decimal("0.0000000001"),
    ],
)
def test_infer_recurring_budget_rejects_invalid_or_unusable_rates(rate):
    with pytest.raises(portfolio_verification.PortfolioInputError):
        portfolio_budget.infer_recurring_budget(
            fixtures.verified_portfolio(),
            rate=rate,
        )


def test_allocate_whole_shares_returns_valid_budget_bounded_quantities():
    prices = {
        "NASDAQ:AAPL": decimal.Decimal("200"),
        "NASDAQ:MSFT": decimal.Decimal("400"),
        "NASDAQ:GOOGL": decimal.Decimal("160"),
    }
    quantities, utilized = portfolio_budget.allocate_whole_shares(
        decimal.Decimal("1000"),
        desired_amounts={
            "NASDAQ:AAPL": decimal.Decimal("400"),
            "NASDAQ:MSFT": decimal.Decimal("350"),
            "NASDAQ:GOOGL": decimal.Decimal("250"),
        },
        prices=prices,
    )

    assert set(quantities) == set(prices)
    assert all(isinstance(quantity, int) and quantity >= 0 for quantity in quantities.values())
    assert utilized == sum(
        (decimal.Decimal(quantities[ticker]) * price for ticker, price in prices.items()),
        decimal.Decimal("0"),
    )
    assert 0 < utilized <= decimal.Decimal("1000")


def test_allocate_whole_shares_can_return_no_purchase():
    quantities, utilized = portfolio_budget.allocate_whole_shares(
        decimal.Decimal("100"),
        desired_amounts={
            "NASDAQ:AAPL": decimal.Decimal("40"),
            "NASDAQ:MSFT": decimal.Decimal("60"),
        },
        prices={
            "NASDAQ:AAPL": decimal.Decimal("200"),
            "NASDAQ:MSFT": decimal.Decimal("300"),
        },
    )

    assert quantities == {"NASDAQ:AAPL": 0, "NASDAQ:MSFT": 0}
    assert utilized == 0


@pytest.mark.parametrize(
    ("budget", "desired", "prices", "selected"),
    [
        (
            decimal.Decimal("20"),
            {
                "NASDAQ:AAPL": decimal.Decimal("6"),
                "NASDAQ:MSFT": decimal.Decimal("11"),
            },
            {
                "NASDAQ:AAPL": decimal.Decimal("10"),
                "NASDAQ:MSFT": decimal.Decimal("20"),
            },
            "NASDAQ:MSFT",
        ),
        (
            decimal.Decimal("10"),
            {
                "NASDAQ:AAPL": decimal.Decimal("6"),
                "NASDAQ:MSFT": decimal.Decimal("6"),
            },
            {
                "NASDAQ:AAPL": decimal.Decimal("10"),
                "NASDAQ:MSFT": decimal.Decimal("10"),
            },
            "NASDAQ:MSFT",
        ),
    ],
)
def test_allocate_whole_shares_uses_documented_ties_independent_of_mapping_order(
    budget,
    desired,
    prices,
    selected,
):
    forward = portfolio_budget.allocate_whole_shares(
        budget,
        desired_amounts=desired,
        prices=prices,
    )
    reverse = portfolio_budget.allocate_whole_shares(
        budget,
        desired_amounts=dict(reversed(desired.items())),
        prices=dict(reversed(prices.items())),
    )

    assert forward == reverse
    assert forward[0][selected] == 1
    assert sum(forward[0].values()) == 1


@pytest.mark.parametrize(
    ("budget", "desired", "prices"),
    [
        (
            decimal.Decimal("0"),
            {"NASDAQ:AAPL": decimal.Decimal("100")},
            {"NASDAQ:AAPL": decimal.Decimal("100")},
        ),
        (decimal.Decimal("100"), {}, {}),
        (
            decimal.Decimal("100"),
            {"NASDAQ:AAPL": decimal.Decimal("100")},
            {"NASDAQ:MSFT": decimal.Decimal("100")},
        ),
        (
            decimal.Decimal("100"),
            {"NASDAQ:AAPL": decimal.Decimal("-1")},
            {"NASDAQ:AAPL": decimal.Decimal("100")},
        ),
        (
            decimal.Decimal("100"),
            {"NASDAQ:AAPL": decimal.Decimal("100")},
            {"NASDAQ:AAPL": decimal.Decimal("0")},
        ),
        (
            decimal.Decimal("100"),
            {
                "NASDAQ:AAPL": decimal.Decimal("100"),
                "NASDAQ:MSFT": decimal.Decimal("100"),
            },
            {
                "NASDAQ:AAPL": decimal.Decimal("60"),
                "NASDAQ:MSFT": decimal.Decimal("60"),
            },
        ),
    ],
)
def test_allocate_whole_shares_rejects_invalid_or_over_budget_requests(
    budget,
    desired,
    prices,
):
    with pytest.raises(ValueError):
        portfolio_budget.allocate_whole_shares(
            budget,
            desired_amounts=desired,
            prices=prices,
        )


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        (decimal.Decimal("1.2345675"), 1.234568),
        (decimal.Decimal("-2.0000006"), -2.000001),
        (decimal.Decimal("0"), 0.0),
    ],
)
def test_round_money_returns_six_decimal_money(amount, expected):
    assert portfolio_budget.round_money(amount) == expected


def test_round_money_rejects_non_finite_values():
    with pytest.raises(ValueError):
        portfolio_budget.round_money(decimal.Decimal("Infinity"))


def test_ai_build_portfolio_filters_zero_positions_and_returns_scratch_target_without_budget():
    result = _invoke_build(
        [fixtures.holding(num_shares=0)],
        country="United States",
        investor_theme="Durable growth with moderate risk.",
        ai=_construction_ai(budget=fixtures.no_budget()),
    )

    assert result.construction_mode == "Scratch"
    assert result.country == "US"
    assert result.verified_seed_holdings == []
    assert len(result.target_portfolio) >= 3
    assert sum(position.allocation for position in result.target_portfolio) == pytest.approx(1)
    assert result.action_plan is None
    assert result.data_gaps
    assert all(reference.is_verified for reference in result.references)


@pytest.mark.parametrize(
    ("theme", "expected_type", "expected_frequency"),
    [
        (
            "Build durable growth with a total budget of USD 1,000.",
            "Total",
            None,
        ),
        (
            "Build durable growth with a recurring USD 1,000 monthly contribution.",
            "Recurring",
            "Monthly",
        ),
    ],
)
def test_ai_build_portfolio_returns_budget_reconciled_whole_share_actions(
    theme,
    expected_type,
    expected_frequency,
):
    budget = portfolio_budget.extract_budget(theme, default_currency="USD")
    result = _invoke_build(
        [],
        country="US",
        investor_theme=theme,
        ai=_construction_ai(budget=budget),
    )

    assert result.action_plan is not None
    assert result.action_plan.budget.budget_type == expected_type
    assert result.action_plan.budget.frequency == expected_frequency
    assert result.action_plan.budget_utilized + result.action_plan.unallocated_amount == pytest.approx(
        result.action_plan.budget.amount
    )
    purchases = [step for step in result.action_plan.steps if step.action == "BUY"]
    assert purchases
    assert all(isinstance(step.quantity, int) and step.quantity > 0 for step in purchases)
    assert all(step.action != "TRIM" for step in result.action_plan.steps)


@pytest.mark.parametrize(
    ("microsoft_price", "expected_budget", "expects_purchase"),
    [
        (200, 200, True),
        (250, 300, True),
        (400, 200, False),
    ],
)
def test_ai_build_portfolio_uses_bounded_inferred_budget_escalation(
    microsoft_price,
    expected_budget,
    expects_purchase,
):
    inferred = portfolio_budget.infer_recurring_budget(
        fixtures.verified_portfolio(),
        rate=decimal.Decimal("0.10"),
    )
    draft = fixtures.draft_data(allocations=[0.1, 0.8, 0.1])
    result = _invoke_build(
        [
            fixtures.holding("NASDAQ:MSFT", num_shares=0),
            fixtures.holding("NASDAQ:AAPL"),
        ],
        country="US",
        investor_theme="Durable growth with moderate risk.",
        ai=_construction_ai(
            budget=inferred,
            mode="Seeded",
            draft_data=draft,
        ),
        prices={
            "NASDAQ:AAPL": 200,
            "NASDAQ:MSFT": microsoft_price,
            "NASDAQ:GOOGL": 1_000,
        },
    )

    assert result.construction_mode == "Seeded"
    assert [holding.ticker for holding in result.verified_seed_holdings] == ["NASDAQ:AAPL"]
    assert result.action_plan is not None
    assert result.action_plan.budget.is_inferred is True
    assert result.action_plan.budget.amount == expected_budget
    has_purchase = any(step.action == "BUY" for step in result.action_plan.steps)
    assert has_purchase is expects_purchase
    if not expects_purchase:
        assert any(step.action == "ACCUMULATE" for step in result.action_plan.steps)


@pytest.mark.parametrize(
    ("portfolio", "country", "theme"),
    [
        ([], "unknown-market", "Durable growth."),
        ([], "US", "   "),
        ([fixtures.holding(num_shares=1.5)], "US", "Durable growth."),
    ],
)
def test_ai_build_portfolio_rejects_invalid_inputs(portfolio, country, theme):
    with pytest.raises(portfolio_verification.PortfolioInputError):
        _invoke_build(
            portfolio,
            country=country,
            investor_theme=theme,
            ai=boundaries.QueuedAI(),
        )


def test_ai_build_portfolio_rejects_budget_currency_mismatch():
    with pytest.raises(portfolio_verification.PortfolioInputError):
        _invoke_build(
            [fixtures.holding()],
            country="US",
            investor_theme="Build a durable portfolio with an AUD 1,000 total budget.",
            ai=boundaries.QueuedAI(),
        )


def test_ai_build_portfolio_reports_target_price_verification_failure():
    theme = "Build a durable growth portfolio with a total budget of USD 1,000."
    budget = portfolio_budget.extract_budget(theme, default_currency="USD")

    with pytest.raises(service.PortfolioConstructionAIError):
        _invoke_build(
            [],
            country="US",
            investor_theme=theme,
            ai=_construction_ai(budget=budget),
            prices={
                "NASDAQ:AAPL": 200,
                "NASDAQ:MSFT": None,
                "NASDAQ:GOOGL": 160,
            },
        )


def test_ai_build_portfolio_reports_ai_provider_failure():
    async def rate_limited(*args, **kwargs):
        del args, kwargs
        raise ai_helper.LLMRateLimitError("retry budget exhausted")

    with pytest.raises(service.PortfolioConstructionAIError):
        _invoke_build(
            [],
            country="US",
            investor_theme="Durable growth with moderate risk.",
            ai=rate_limited,
        )


def test_ai_build_portfolio_rejects_invalid_structured_ai_output():
    with pytest.raises(service.PortfolioConstructionAIError):
        _invoke_build(
            [],
            country="US",
            investor_theme="Durable growth with moderate risk.",
            ai=boundaries.QueuedAI(boundaries.AIResponse({"unexpected": "response"})),
        )


def test_ai_build_portfolio_retains_unmatched_structural_sources_as_unverified():
    result = _invoke_build(
        [],
        country="US",
        investor_theme="Durable growth with moderate risk.",
        ai=_construction_ai(
            budget=fixtures.no_budget(),
            citation_urls=(),
        ),
    )

    assert result.references
    assert all(reference.is_verified is False for reference in result.references)
    assert result.construction_status == "CompleteWithWarnings"
    assert result.validation_warnings


def test_ai_build_portfolio_repeated_calls_return_equal_public_results():
    theme = "Durable growth with a total budget of USD 1,000."
    budget = portfolio_budget.extract_budget(theme, default_currency="USD")
    cache = boundaries.MemoryCache()
    first = _invoke_build(
        [],
        country="US",
        investor_theme=theme,
        ai=_construction_ai(budget=budget),
        cache=cache,
    )
    second = _invoke_build(
        [],
        country="US",
        investor_theme=theme,
        ai=boundaries.QueuedAI(),
        cache=cache,
        market=boundaries.failing_market,
    )

    assert second == first


def test_ai_build_portfolio_rejects_an_opaque_invalid_cached_result():
    cache = boundaries.MemoryCache()
    _invoke_build(
        [],
        country="US",
        investor_theme="Durable growth with moderate risk.",
        ai=_construction_ai(budget=fixtures.no_budget()),
        cache=cache,
    )
    cache.corrupt_latest({"invalid": "cached construction"})

    with pytest.raises(RuntimeError):
        _invoke_build(
            [],
            country="US",
            investor_theme="Durable growth with moderate risk.",
            ai=boundaries.QueuedAI(),
            cache=cache,
            market=boundaries.failing_market,
        )


def test_ai_build_portfolio_refreshes_public_market_values_after_cache_expiry():
    theme = "Durable growth with a total budget of USD 1,000."
    budget = portfolio_budget.extract_budget(theme, default_currency="USD")
    cache = boundaries.MemoryCache()
    first = _invoke_build(
        [fixtures.holding("NASDAQ:AAPL")],
        country="US",
        investor_theme=theme,
        ai=_construction_ai(budget=budget, mode="Seeded"),
        cache=cache,
    )
    cache.advance(3601)
    second = _invoke_build(
        [fixtures.holding("NASDAQ:AAPL")],
        country="US",
        investor_theme=theme,
        ai=_construction_ai(budget=budget, mode="Seeded"),
        prices={
            **_DEFAULT_PRICES,
            "NASDAQ:AAPL": 250,
        },
        cache=cache,
    )

    assert first.verified_seed_holdings[0].market_price == 200
    assert second.verified_seed_holdings[0].market_price == 250
    assert second != first
