import asyncio
from datetime import UTC, datetime
from unittest import mock

import pytest
from pydantic import ValidationError

from app.models import portfolio as models_portfolio
from app.services import portfolio_verification as service
from tests import portfolio_service_fixtures as boundaries


def _holding(
    ticker: str = "AAPL",
    *,
    num_shares: float = 10,
    market_price: float | None = 190,
) -> models_portfolio.PortfolioHolding:
    return models_portfolio.PortfolioHolding(
        ticker=ticker,
        num_shares=num_shares,
        avg_price=150,
        market_price=market_price,
        target_allocation=0.6,
        tags="growth",
    )


def _verified_holding(
    ticker: str = "NASDAQ:AAPL",
    *,
    currency: str = "USD",
    allocation: float = 1,
) -> models_portfolio.PortfolioVerifiedHolding:
    exchange, symbol = ticker.split(":", 1)
    return models_portfolio.PortfolioVerifiedHolding(
        ticker=ticker,
        company_name=f"{symbol} Incorporated",
        exchange=exchange,
        currency=currency,
        num_shares=10,
        avg_price=150,
        market_price=200,
        price_source="MarketData",
        market_value=2_000,
        current_allocation=allocation,
        target_allocation=0.6,
        allocation_drift=allocation - 0.6,
        unrealized_profit_loss=500,
        tags="growth",
    )


def _security_quote(
    ticker: str = "NASDAQ:AAPL",
    *,
    currency: str = "USD",
) -> service.VerifiedSecurityQuote:
    exchange, symbol = ticker.split(":", 1)
    return service.VerifiedSecurityQuote(
        requested_ticker=ticker,
        symbol=symbol,
        ticker=ticker,
        company_name=f"{symbol} Incorporated",
        exchange=exchange,
        currency=currency,
        quote_type="EQUITY",
        market_price=200,
    )


def _invoke_portfolio(
    portfolio,
    *,
    country: str,
    market,
    cache: boundaries.MemoryCache | None = None,
):
    memory_cache = cache or boundaries.MemoryCache()
    with (
        mock.patch.object(service.cache, "get", new=memory_cache.get),
        mock.patch.object(service.cache, "set", new=memory_cache.set),
        mock.patch.object(service.services_stock, "resolve_symbol", new=market),
    ):
        return asyncio.run(service.verify_portfolio(portfolio, country=country))


def _invoke_quotes(
    tickers,
    *,
    country: str,
    market,
    cache: boundaries.MemoryCache | None = None,
):
    memory_cache = cache or boundaries.MemoryCache()
    with (
        mock.patch.object(service.cache, "get", new=memory_cache.get),
        mock.patch.object(service.cache, "set", new=memory_cache.set),
        mock.patch.object(service.services_stock, "resolve_symbol", new=market),
    ):
        return asyncio.run(service.verify_security_quotes(tickers, country=country))


@pytest.mark.parametrize("case", ["naive-time", "duplicate-ticker", "allocation-total"])
def test_verified_portfolio_validates_snapshot_invariants(case):
    holdings = [_verified_holding()]
    as_of = datetime(2026, 8, 21, tzinfo=UTC)
    if case == "naive-time":
        as_of = datetime(2026, 8, 21)
    elif case == "duplicate-ticker":
        holdings = [
            _verified_holding(allocation=0.5),
            _verified_holding(allocation=0.5),
        ]
    else:
        holdings = [_verified_holding(allocation=0.8)]

    with pytest.raises(ValidationError):
        service.VerifiedPortfolio(
            as_of=as_of,
            country="US",
            currency="USD",
            total_market_value=2_000,
            holdings=holdings,
            data_gaps=[],
        )


@pytest.mark.parametrize("case", ["naive-time", "duplicate-ticker", "mixed-currency"])
def test_verified_security_quotes_validates_collection_invariants(case):
    securities = [_security_quote()]
    as_of = datetime(2026, 8, 21, tzinfo=UTC)
    if case == "naive-time":
        as_of = datetime(2026, 8, 21)
    elif case == "duplicate-ticker":
        securities = [_security_quote(), _security_quote()]
    else:
        securities = [
            _security_quote(),
            _security_quote("ASX:CBA", currency="AUD"),
        ]

    with pytest.raises(ValidationError):
        service.VerifiedSecurityQuotes(
            as_of=as_of,
            country="US",
            currency="USD",
            securities=securities,
        )


def test_verify_portfolio_canonicalizes_country_and_prefers_current_market_price():
    market = boundaries.market_resolver({"NASDAQ:AAPL": 200})
    result = _invoke_portfolio(
        [_holding()],
        country="United States",
        market=market,
    )

    holding = result.holdings[0]
    assert result.country == "US"
    assert result.currency == "USD"
    assert result.total_market_value == 2_000
    assert holding.ticker == "NASDAQ:AAPL"
    assert holding.market_price == 200
    assert holding.price_source == "MarketData"
    assert holding.current_allocation == 1
    assert holding.allocation_drift == pytest.approx(0.4)
    assert holding.unrealized_profit_loss == 500
    assert result.data_gaps == []


def test_verify_portfolio_uses_client_price_only_when_market_price_is_missing():
    market = boundaries.market_resolver({"NASDAQ:AAPL": None})
    result = _invoke_portfolio(
        [_holding(market_price=190)],
        country="US",
        market=market,
    )

    assert result.holdings[0].market_price == 190
    assert result.holdings[0].price_source == "Client"
    assert result.data_gaps
    assert "NASDAQ:AAPL" in result.data_gaps[0]


def test_verify_portfolio_rejects_a_holding_without_provider_or_client_price():
    market = boundaries.market_resolver({"NASDAQ:AAPL": None})

    with pytest.raises(service.PortfolioInputError):
        _invoke_portfolio(
            [_holding(market_price=None)],
            country="US",
            market=market,
        )


def test_verify_portfolio_rejects_unsupported_security_types():
    market = boundaries.market_resolver(
        {"NASDAQ:AAPL": 200},
        quote_types={"NASDAQ:AAPL": "CRYPTOCURRENCY"},
    )

    with pytest.raises(service.PortfolioInputError):
        _invoke_portfolio(
            [_holding()],
            country="US",
            market=market,
        )


@pytest.mark.parametrize(
    ("portfolio", "country"),
    [
        ([], "US"),
        ([_holding(num_shares=0)], "US"),
        ([_holding()], "unknown-market"),
        ([_holding(f"NASDAQ:TEST{index}") for index in range(51)], "US"),
    ],
)
def test_verify_portfolio_rejects_invalid_business_inputs(portfolio, country):
    market = boundaries.market_resolver({"NASDAQ:AAPL": 200})

    with pytest.raises(service.PortfolioInputError):
        _invoke_portfolio(
            portfolio,
            country=country,
            market=market,
        )


def test_verify_portfolio_rejects_duplicate_provider_canonical_tickers():
    market = boundaries.market_resolver({"NASDAQ:AAPL": 200})

    with pytest.raises(service.PortfolioInputError):
        _invoke_portfolio(
            [_holding("AAPL"), _holding("NASDAQ:AAPL")],
            country="US",
            market=market,
        )


def test_verify_portfolio_rejects_mixed_verified_currencies():
    market = boundaries.market_resolver(
        {
            "NASDAQ:AAPL": 200,
            "NASDAQ:MSFT": 400,
        },
        currencies={"NASDAQ:MSFT": "AUD"},
    )

    with pytest.raises(service.PortfolioInputError):
        _invoke_portfolio(
            [_holding("NASDAQ:AAPL"), _holding("NASDAQ:MSFT")],
            country="US",
            market=market,
        )


def test_verify_portfolio_reports_market_provider_failures():
    market = boundaries.market_resolver(
        {"NASDAQ:AAPL": 200},
        failures={"NASDAQ:AAPL": OSError("provider unavailable")},
    )

    with pytest.raises(service.PortfolioVerificationError):
        _invoke_portfolio(
            [_holding("NASDAQ:AAPL")],
            country="US",
            market=market,
        )


def test_verify_portfolio_repeated_calls_return_equal_public_snapshots():
    cache = boundaries.MemoryCache()
    first = _invoke_portfolio(
        [_holding()],
        country="US",
        market=boundaries.market_resolver({"NASDAQ:AAPL": 200}),
        cache=cache,
    )
    second = _invoke_portfolio(
        [_holding()],
        country="US",
        market=boundaries.failing_market,
        cache=cache,
    )

    assert second == first
    assert second is not first


def test_verify_portfolio_rejects_an_opaque_invalid_cached_snapshot():
    cache = boundaries.MemoryCache()
    _invoke_portfolio(
        [_holding()],
        country="US",
        market=boundaries.market_resolver({"NASDAQ:AAPL": 200}),
        cache=cache,
    )
    cache.corrupt_latest({"invalid": "cached portfolio"})

    with pytest.raises(RuntimeError):
        _invoke_portfolio(
            [_holding()],
            country="US",
            market=boundaries.failing_market,
            cache=cache,
        )


def test_verify_portfolio_refreshes_market_values_after_cache_expiry():
    cache = boundaries.MemoryCache()
    first = _invoke_portfolio(
        [_holding()],
        country="US",
        market=boundaries.market_resolver({"NASDAQ:AAPL": 200}),
        cache=cache,
    )
    cache.advance(301)
    second = _invoke_portfolio(
        [_holding()],
        country="US",
        market=boundaries.market_resolver({"NASDAQ:AAPL": 250}),
        cache=cache,
    )

    assert first.total_market_value == 2_000
    assert second.total_market_value == 2_500
    assert second.holdings[0].market_price == 250


def test_verify_security_quotes_returns_canonical_quotes_in_documented_order():
    market = boundaries.market_resolver(
        {
            "NASDAQ:AAPL": 200,
            "NYSE:SGOV": 100.65,
        },
        quote_types={"NYSE:SGOV": "ETF"},
    )
    result = _invoke_quotes(
        ["NYSEARCA:SGOV", "NASDAQ:AAPL"],
        country="United States",
        market=market,
    )

    assert result.country == "US"
    assert result.currency == "USD"
    assert [quote.ticker for quote in result.securities] == [
        "NASDAQ:AAPL",
        "NYSE:SGOV",
    ]
    assert [quote.requested_ticker for quote in result.securities] == [
        "NASDAQ:AAPL",
        "NYSE:SGOV",
    ]
    assert [quote.market_price for quote in result.securities] == [200, 100.65]


@pytest.mark.parametrize(
    "tickers",
    [
        [],
        ["NASDAQ:AAPL", "nasdaq:aapl"],
        ["NYSEARCA:SGOV", "NYSE:SGOV"],
        ["AAPL"],
        [f"NASDAQ:TEST{index}" for index in range(21)],
    ],
)
def test_verify_security_quotes_rejects_invalid_ticker_requests(tickers):
    market = boundaries.market_resolver({"NASDAQ:AAPL": 200})

    with pytest.raises(service.PortfolioInputError):
        _invoke_quotes(
            tickers,
            country="US",
            market=market,
        )


def test_verify_security_quotes_rejects_provider_canonical_duplicates():
    market = boundaries.market_resolver(
        {
            "NASDAQ:AAPL": 200,
            "NASDAQ:MSFT": 400,
        },
        canonical_tickers={"NASDAQ:MSFT": "NASDAQ:AAPL"},
    )

    with pytest.raises(service.PortfolioInputError):
        _invoke_quotes(
            ["NASDAQ:AAPL", "NASDAQ:MSFT"],
            country="US",
            market=market,
        )


@pytest.mark.parametrize("price", [None, 0, -1, float("inf"), float("nan")])
def test_verify_security_quotes_requires_positive_finite_market_prices(price):
    market = boundaries.market_resolver({"NASDAQ:AAPL": price})

    with pytest.raises(service.PortfolioInputError):
        _invoke_quotes(
            ["NASDAQ:AAPL"],
            country="US",
            market=market,
        )


def test_verify_security_quotes_rejects_mixed_currencies():
    market = boundaries.market_resolver(
        {
            "NASDAQ:AAPL": 200,
            "NASDAQ:MSFT": 400,
        },
        currencies={"NASDAQ:MSFT": "AUD"},
    )

    with pytest.raises(service.PortfolioInputError):
        _invoke_quotes(
            ["NASDAQ:AAPL", "NASDAQ:MSFT"],
            country="US",
            market=market,
        )


def test_verify_security_quotes_rejects_unsupported_security_types():
    market = boundaries.market_resolver(
        {"NASDAQ:AAPL": 200},
        quote_types={"NASDAQ:AAPL": "CRYPTOCURRENCY"},
    )

    with pytest.raises(service.PortfolioInputError):
        _invoke_quotes(
            ["NASDAQ:AAPL"],
            country="US",
            market=market,
        )


def test_verify_security_quotes_reports_market_provider_failures():
    market = boundaries.market_resolver(
        {"NASDAQ:AAPL": 200},
        failures={"NASDAQ:AAPL": OSError("provider unavailable")},
    )

    with pytest.raises(service.PortfolioVerificationError):
        _invoke_quotes(
            ["NASDAQ:AAPL"],
            country="US",
            market=market,
        )


def test_verify_security_quotes_repeated_calls_return_equal_public_results():
    cache = boundaries.MemoryCache()
    first = _invoke_quotes(
        ["NASDAQ:AAPL"],
        country="US",
        market=boundaries.market_resolver({"NASDAQ:AAPL": 200}),
        cache=cache,
    )
    second = _invoke_quotes(
        ["NASDAQ:AAPL"],
        country="US",
        market=boundaries.failing_market,
        cache=cache,
    )

    assert second == first
    assert second is not first


def test_verify_security_quotes_rejects_an_opaque_invalid_cached_collection():
    cache = boundaries.MemoryCache()
    _invoke_quotes(
        ["NASDAQ:AAPL"],
        country="US",
        market=boundaries.market_resolver({"NASDAQ:AAPL": 200}),
        cache=cache,
    )
    cache.corrupt_latest({"invalid": "cached quotes"})

    with pytest.raises(RuntimeError):
        _invoke_quotes(
            ["NASDAQ:AAPL"],
            country="US",
            market=boundaries.failing_market,
            cache=cache,
        )


def test_verify_security_quotes_refreshes_prices_after_cache_expiry():
    cache = boundaries.MemoryCache()
    first = _invoke_quotes(
        ["NASDAQ:AAPL"],
        country="US",
        market=boundaries.market_resolver({"NASDAQ:AAPL": 200}),
        cache=cache,
    )
    cache.advance(301)
    second = _invoke_quotes(
        ["NASDAQ:AAPL"],
        country="US",
        market=boundaries.market_resolver({"NASDAQ:AAPL": 250}),
        cache=cache,
    )

    assert first.securities[0].market_price == 200
    assert second.securities[0].market_price == 250


def test_verify_candidate_identities_returns_partial_canonical_results_in_request_order():
    market = boundaries.market_resolver(
        {
            "NYSE:SGOV": None,
            "ASX:CBA": 150,
            "NASDAQ:GOVT": 23.45,
        },
        currencies={"ASX:CBA": "AUD"},
        canonical_tickers={"NASDAQ:GOVT": "NYSE:SGOV"},
        quote_types={
            "NYSE:SGOV": "ETF",
            "NASDAQ:GOVT": "ETF",
        },
    )
    with mock.patch.object(service.services_stock, "resolve_symbol", new=market):
        result = service.verify_candidate_identities(
            ["NYSEARCA:SGOV", "ASX:CBA", "NASDAQ:GOVT"],
            country="United States",
            expected_currency="usd",
        )

    assert [identity.ticker for identity in result.identities] == ["NYSE:SGOV"]
    assert result.identities[0].requested_ticker == "NYSE:SGOV"
    assert result.rejected_tickers == ("ASX:CBA", "NASDAQ:GOVT")


def test_verify_candidate_identities_keeps_valid_candidates_after_provider_failure():
    market = boundaries.market_resolver(
        {
            "NASDAQ:AAPL": 200,
            "NASDAQ:MSFT": None,
        },
        failures={"NASDAQ:AAPL": OSError("provider unavailable")},
    )
    with mock.patch.object(service.services_stock, "resolve_symbol", new=market):
        result = service.verify_candidate_identities(
            ["NASDAQ:AAPL", "NASDAQ:MSFT"],
            country="US",
            expected_currency="USD",
        )

    assert [identity.ticker for identity in result.identities] == ["NASDAQ:MSFT"]
    assert result.rejected_tickers == ("NASDAQ:AAPL",)


def test_verify_candidate_identities_accepts_supported_security_without_a_price():
    market = boundaries.market_resolver({"NASDAQ:AAPL": None})
    with mock.patch.object(service.services_stock, "resolve_symbol", new=market):
        result = service.verify_candidate_identities(
            ["NASDAQ:AAPL"],
            country="US",
            expected_currency="USD",
        )

    assert [identity.ticker for identity in result.identities] == ["NASDAQ:AAPL"]
    assert result.rejected_tickers == ()


def test_verify_candidate_identities_rejects_unsupported_security_types():
    market = boundaries.market_resolver(
        {"NASDAQ:AAPL": None},
        quote_types={"NASDAQ:AAPL": "CRYPTOCURRENCY"},
    )
    with mock.patch.object(service.services_stock, "resolve_symbol", new=market):
        result = service.verify_candidate_identities(
            ["NASDAQ:AAPL"],
            country="US",
            expected_currency="USD",
        )

    assert result.identities == ()
    assert result.rejected_tickers == ("NASDAQ:AAPL",)


@pytest.mark.parametrize(
    ("tickers", "country", "currency"),
    [
        (["AAPL"], "US", "USD"),
        (["NASDAQ:AAPL"], "unknown-market", "USD"),
        (["NASDAQ:AAPL"], "US", "$$$"),
    ],
)
def test_verify_candidate_identities_rejects_invalid_request_metadata(
    tickers,
    country,
    currency,
):
    market = boundaries.market_resolver({"NASDAQ:AAPL": 200})

    with (
        mock.patch.object(service.services_stock, "resolve_symbol", new=market),
        pytest.raises(service.PortfolioInputError),
    ):
        service.verify_candidate_identities(
            tickers,
            country=country,
            expected_currency=currency,
        )
