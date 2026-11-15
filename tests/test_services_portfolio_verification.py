import asyncio
from unittest import mock

import pytest

from app.models import portfolio as models_portfolio
from app.services import portfolio_verification as service
from app.services import stock as services_stock


def _resolved_symbol(
    *,
    symbol: str,
    price: float | None,
    currency: str = "USD",
    exchange: str = "NASDAQ",
    normalized_symbol: str | None = None,
    quote_type: str = "EQUITY",
) -> services_stock.ResolvedSymbol:
    return services_stock.ResolvedSymbol(
        symbol=symbol,
        normalized_symbol=normalized_symbol or f"{exchange}:{symbol}",
        exchange=exchange,
        country="US",
        currency=currency,
        quote_type=quote_type,
        company_name=f"{symbol} Incorporated",
        market_price=price,
    )


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


def test_verify_portfolio_canonicalizes_country_and_prefers_current_market_price():
    with (
        mock.patch.object(service.cache, "get", new_callable=mock.AsyncMock, return_value=None),
        mock.patch.object(service.cache, "set", new_callable=mock.AsyncMock, return_value=True) as cache_set,
        mock.patch.object(
            service.services_stock,
            "resolve_symbol",
            return_value=_resolved_symbol(symbol="AAPL", price=200),
        ),
    ):
        result = asyncio.run(
            service.verify_portfolio(
                [_holding()],
                country="United States",
            )
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
    assert cache_set.await_args.kwargs["ttl"] == 5 * 60


def test_verify_portfolio_uses_client_price_only_when_current_price_is_missing():
    with (
        mock.patch.object(service.cache, "get", new_callable=mock.AsyncMock, return_value=None),
        mock.patch.object(service.cache, "set", new_callable=mock.AsyncMock, return_value=True),
        mock.patch.object(
            service.services_stock,
            "resolve_symbol",
            return_value=_resolved_symbol(symbol="AAPL", price=None),
        ),
    ):
        result = asyncio.run(service.verify_portfolio([_holding(market_price=190)], country="US"))

    assert result.holdings[0].market_price == 190
    assert result.holdings[0].price_source == "Client"
    assert "client-supplied market price" in result.data_gaps[0]


@pytest.mark.parametrize(
    ("portfolio", "country", "message"),
    [
        ([], "US", "at least one"),
        ([_holding(num_shares=0)], "US", "positive-share"),
        ([_holding()], "unknown-market", "Unsupported or unknown country"),
    ],
)
def test_verify_portfolio_rejects_invalid_business_inputs_before_market_resolution(
    portfolio,
    country,
    message,
):
    with (
        mock.patch.object(service.cache, "get", new_callable=mock.AsyncMock, return_value=None),
        mock.patch.object(service.services_stock, "resolve_symbol") as resolve_symbol,
        pytest.raises(service.PortfolioInputError, match=message),
    ):
        asyncio.run(service.verify_portfolio(portfolio, country=country))

    resolve_symbol.assert_not_called()


def test_verify_portfolio_rejects_more_than_50_holdings_before_cache_or_provider_work():
    portfolio = [_holding(f"NASDAQ:TEST{index}") for index in range(51)]
    with (
        mock.patch.object(service.cache, "get", new_callable=mock.AsyncMock) as cache_get,
        mock.patch.object(service.cache, "set", new_callable=mock.AsyncMock) as cache_set,
        mock.patch.object(service.services_stock, "resolve_symbol") as resolve_symbol,
        pytest.raises(service.PortfolioInputError, match="at most 50"),
    ):
        asyncio.run(service.verify_portfolio(portfolio, country="US"))

    cache_get.assert_not_awaited()
    cache_set.assert_not_awaited()
    resolve_symbol.assert_not_called()


def test_verify_portfolio_rejects_duplicate_provider_canonical_tickers():
    positions = [_holding("AAPL"), _holding("NASDAQ:AAPL")]
    with (
        mock.patch.object(service.cache, "get", new_callable=mock.AsyncMock, return_value=None),
        mock.patch.object(
            service.services_stock,
            "resolve_symbol",
            return_value=_resolved_symbol(symbol="AAPL", price=200),
        ),
        pytest.raises(service.PortfolioInputError, match="Duplicate portfolio ticker"),
    ):
        asyncio.run(service.verify_portfolio(positions, country="US"))


def test_verify_portfolio_rejects_mixed_verified_currencies():
    positions = [_holding("NASDAQ:AAPL"), _holding("NASDAQ:MSFT")]
    with (
        mock.patch.object(service.cache, "get", new_callable=mock.AsyncMock, return_value=None),
        mock.patch.object(
            service.services_stock,
            "resolve_symbol",
            side_effect=[
                _resolved_symbol(symbol="AAPL", price=200),
                _resolved_symbol(symbol="MSFT", price=400, currency="AUD"),
            ],
        ),
        pytest.raises(service.PortfolioInputError, match="Mixed-currency"),
    ):
        asyncio.run(service.verify_portfolio(positions, country="US"))


def test_verify_portfolio_reports_market_provider_failures():
    with (
        mock.patch.object(service.cache, "get", new_callable=mock.AsyncMock, return_value=None),
        mock.patch.object(
            service.services_stock,
            "resolve_symbol",
            side_effect=OSError("provider unavailable"),
        ),
        pytest.raises(service.PortfolioVerificationError, match="Unable to verify ticker"),
    ):
        asyncio.run(service.verify_portfolio([_holding()], country="US"))


def test_verify_portfolio_returns_validated_cached_snapshot_without_market_call():
    expected = service.VerifiedPortfolio(
        as_of="2026-08-21T00:00:00Z",
        country="US",
        currency="USD",
        total_market_value=2_000,
        holdings=[
            models_portfolio.PortfolioVerifiedHolding(
                ticker="NASDAQ:AAPL",
                company_name="Apple Inc.",
                exchange="NASDAQ",
                currency="USD",
                num_shares=10,
                avg_price=150,
                market_price=200,
                price_source="MarketData",
                market_value=2_000,
                current_allocation=1,
                target_allocation=0.6,
                allocation_drift=0.4,
                unrealized_profit_loss=500,
                tags="growth",
            )
        ],
        data_gaps=[],
    )
    with (
        mock.patch.object(
            service.cache,
            "get",
            new_callable=mock.AsyncMock,
            return_value=expected.model_dump(mode="json"),
        ),
        mock.patch.object(service.services_stock, "resolve_symbol") as resolve_symbol,
    ):
        result = asyncio.run(service.verify_portfolio([_holding()], country="US"))

    assert result == expected
    assert result is not expected
    resolve_symbol.assert_not_called()


def test_verify_portfolio_rejects_invalid_cached_data():
    with (
        mock.patch.object(
            service.cache,
            "get",
            new_callable=mock.AsyncMock,
            return_value={"country": "US"},
        ),
        pytest.raises(RuntimeError, match="cache contains an invalid value"),
    ):
        asyncio.run(service.verify_portfolio([_holding()], country="US"))


def test_verify_security_quotes_returns_canonical_positive_single_currency_quotes():
    resolved_by_ticker = {
        "NASDAQ:AAPL": _resolved_symbol(symbol="AAPL", price=200),
        "NYSE:SGOV": _resolved_symbol(
            symbol="SGOV",
            price=100.65,
            exchange="NYSE",
            normalized_symbol="NYSE:SGOV",
            quote_type="ETF",
        ),
    }
    with (
        mock.patch.object(service.cache, "get", new_callable=mock.AsyncMock, return_value=None),
        mock.patch.object(service.cache, "set", new_callable=mock.AsyncMock, return_value=True),
        mock.patch.object(
            service.services_stock,
            "resolve_symbol",
            side_effect=lambda ticker: resolved_by_ticker[ticker],
        ),
    ):
        result = asyncio.run(
            service.verify_security_quotes(
                ["NYSEARCA:SGOV", "NASDAQ:AAPL"],
                country="United States",
            )
        )

    assert result.country == "US"
    assert result.currency == "USD"
    assert [quote.ticker for quote in result.securities] == ["NASDAQ:AAPL", "NYSE:SGOV"]
    assert [quote.market_price for quote in result.securities] == [200, 100.65]


@pytest.mark.parametrize(
    ("tickers", "message"),
    [
        ([], "At least one"),
        (["NASDAQ:AAPL", "nasdaq:aapl"], "unique"),
        (["NYSEARCA:SGOV", "NYSE:SGOV"], "unique"),
        (["AAPL"], "EXCHANGE:CODE"),
    ],
)
def test_verify_security_quotes_rejects_missing_duplicate_or_malformed_tickers(tickers, message):
    with (
        mock.patch.object(service.services_stock, "resolve_symbol") as resolve_symbol,
        pytest.raises(service.PortfolioInputError, match=message),
    ):
        asyncio.run(service.verify_security_quotes(tickers, country="US"))

    resolve_symbol.assert_not_called()


def test_verify_security_quotes_rejects_more_than_20_tickers_before_cache_or_provider_work():
    tickers = [f"NASDAQ:TEST{index}" for index in range(21)]
    with (
        mock.patch.object(service.cache, "get", new_callable=mock.AsyncMock) as cache_get,
        mock.patch.object(service.cache, "set", new_callable=mock.AsyncMock) as cache_set,
        mock.patch.object(service.services_stock, "resolve_symbol") as resolve_symbol,
        pytest.raises(service.PortfolioInputError, match="At most 20"),
    ):
        asyncio.run(service.verify_security_quotes(tickers, country="US"))

    cache_get.assert_not_awaited()
    cache_set.assert_not_awaited()
    resolve_symbol.assert_not_called()


@pytest.mark.parametrize("price", [None, 0, -1])
def test_verify_security_quotes_requires_a_positive_current_market_price(price):
    with (
        mock.patch.object(service.cache, "get", new_callable=mock.AsyncMock, return_value=None),
        mock.patch.object(
            service.services_stock,
            "resolve_symbol",
            return_value=_resolved_symbol(symbol="AAPL", price=price),
        ),
        pytest.raises(service.PortfolioInputError, match="current market price"),
    ):
        asyncio.run(service.verify_security_quotes(["NASDAQ:AAPL"], country="US"))


def test_verify_security_quotes_rejects_mixed_currencies():
    with (
        mock.patch.object(service.cache, "get", new_callable=mock.AsyncMock, return_value=None),
        mock.patch.object(
            service.services_stock,
            "resolve_symbol",
            side_effect=[
                _resolved_symbol(symbol="AAPL", price=200),
                _resolved_symbol(symbol="MSFT", price=400, currency="AUD"),
            ],
        ),
        pytest.raises(service.PortfolioInputError, match="Mixed-currency"),
    ):
        asyncio.run(
            service.verify_security_quotes(
                ["NASDAQ:AAPL", "NASDAQ:MSFT"],
                country="US",
            )
        )


def test_verify_security_quotes_returns_validated_cache_without_market_call():
    expected = service.VerifiedSecurityQuotes(
        as_of="2026-08-21T00:00:00Z",
        country="US",
        currency="USD",
        securities=[
            service.VerifiedSecurityQuote(
                requested_ticker="NASDAQ:AAPL",
                symbol="AAPL",
                ticker="NASDAQ:AAPL",
                company_name="Apple Inc.",
                exchange="NASDAQ",
                currency="USD",
                quote_type="EQUITY",
                market_price=200,
            )
        ],
    )
    with (
        mock.patch.object(
            service.cache,
            "get",
            new_callable=mock.AsyncMock,
            return_value=expected.model_dump(mode="json"),
        ),
        mock.patch.object(service.services_stock, "resolve_symbol") as resolve_symbol,
    ):
        result = asyncio.run(service.verify_security_quotes(["NASDAQ:AAPL"], country="US"))

    assert result == expected
    assert result is not expected
    resolve_symbol.assert_not_called()


def test_verify_security_quotes_rejects_invalid_cached_data():
    with (
        mock.patch.object(
            service.cache,
            "get",
            new_callable=mock.AsyncMock,
            return_value={"country": "US"},
        ),
        pytest.raises(RuntimeError, match="cache contains an invalid value"),
    ):
        asyncio.run(service.verify_security_quotes(["NASDAQ:AAPL"], country="US"))


def test_verify_candidate_identities_returns_partial_canonical_results_in_request_order():
    def resolve_candidate(ticker: str) -> services_stock.ResolvedSymbol:
        if ticker == "NYSE:SGOV":
            return _resolved_symbol(
                symbol="SGOV",
                price=None,
                exchange="NYSE",
                normalized_symbol="NYSE:SGOV",
                quote_type="ETF",
            )
        if ticker == "ASX:CBA":
            return _resolved_symbol(
                symbol="CBA.AX",
                price=150,
                currency="AUD",
                exchange="ASX",
                normalized_symbol="ASX:CBA",
            )
        return _resolved_symbol(
            symbol="GOVT",
            price=23.45,
            exchange="NASDAQ",
            normalized_symbol="NYSE:SGOV",
            quote_type="ETF",
        )

    with mock.patch.object(
        service.services_stock,
        "resolve_symbol",
        side_effect=resolve_candidate,
    ):
        result = service.verify_candidate_identities(
            ["NYSEARCA:SGOV", "ASX:CBA", "NASDAQ:GOVT"],
            country="United States",
            expected_currency="usd",
        )

    assert [identity.ticker for identity in result.identities] == ["NYSE:SGOV"]
    assert result.identities[0].requested_ticker == "NYSE:SGOV"
    assert result.rejected_tickers == ("ASX:CBA", "NASDAQ:GOVT")


def test_verify_candidate_identities_rejects_provider_failures_without_losing_other_candidates():
    with mock.patch.object(
        service.services_stock,
        "resolve_symbol",
        side_effect=[
            OSError("provider unavailable"),
            _resolved_symbol(symbol="MSFT", price=None),
        ],
    ):
        result = service.verify_candidate_identities(
            ["NASDAQ:AAPL", "NASDAQ:MSFT"],
            country="US",
            expected_currency="USD",
        )

    assert [identity.ticker for identity in result.identities] == ["NASDAQ:MSFT"]
    assert result.rejected_tickers == ("NASDAQ:AAPL",)


@pytest.mark.parametrize(
    ("tickers", "country", "currency", "message"),
    [
        (["AAPL"], "US", "USD", "EXCHANGE:CODE"),
        (["NASDAQ:AAPL"], "unknown-market", "USD", "Unsupported or unknown country"),
        (["NASDAQ:AAPL"], "US", "$$$", "three-letter"),
    ],
)
def test_verify_candidate_identities_rejects_invalid_request_metadata(
    tickers,
    country,
    currency,
    message,
):
    with (
        mock.patch.object(service.services_stock, "resolve_symbol") as resolve_symbol,
        pytest.raises(service.PortfolioInputError, match=message),
    ):
        service.verify_candidate_identities(
            tickers,
            country=country,
            expected_currency=currency,
        )

    resolve_symbol.assert_not_called()
