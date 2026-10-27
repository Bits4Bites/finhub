import asyncio
from unittest.mock import AsyncMock, patch

from app.models import portfolio as models_portfolio
from app.services import portfolio_verification
from app.services import stock as services_stock


def _resolved_symbol(
    *,
    symbol: str,
    price: float | None,
    currency: str = "USD",
    exchange: str = "NASDAQ",
    normalized_symbol: str | None = None,
) -> services_stock.ResolvedSymbol:
    return services_stock.ResolvedSymbol(
        symbol=symbol,
        normalized_symbol=normalized_symbol or f"{exchange}:{symbol}",
        exchange=exchange,
        country="US",
        currency=currency,
        quote_type="EQUITY",
        company_name=f"{symbol} Incorporated",
        market_price=price,
    )


def test_build_verified_security_quotes_uses_market_data_without_holdings():
    with patch.object(
        portfolio_verification.services_stock,
        "resolve_symbol",
        side_effect=[
            _resolved_symbol(symbol="AAPL", price=200),
            _resolved_symbol(symbol="MSFT", price=400),
        ],
    ):
        result = portfolio_verification._build_verified_security_quotes(
            ["NASDAQ:AAPL", "NASDAQ:MSFT"],
            country="US",
        )

    assert result.currency == "USD"
    assert [security.ticker for security in result.securities] == [
        "NASDAQ:AAPL",
        "NASDAQ:MSFT",
    ]
    assert [security.market_price for security in result.securities] == [200, 400]


def test_load_security_quote_normalizes_nyse_arca_alias():
    resolved = _resolved_symbol(
        symbol="SGOV",
        price=100.65,
        exchange="NYSE",
        normalized_symbol="NYSE:SGOV",
    )
    with patch.object(
        portfolio_verification.services_stock,
        "resolve_symbol",
        return_value=resolved,
    ) as mock_resolve:
        quote, used_fallback = portfolio_verification._load_security_quote("NYSEARCA:SGOV")

    mock_resolve.assert_called_once_with("NYSEARCA:SGOV")
    assert quote.requested_ticker == "NYSEARCA:SGOV"
    assert quote.symbol == "SGOV"
    assert quote.ticker == "NYSE:SGOV"
    assert quote.market_price == 100.65
    assert used_fallback is False


def test_verify_security_quotes_returns_cached_snapshot_without_market_call():
    expected = portfolio_verification.VerifiedSecurityQuotes(
        as_of="2026-08-21T00:00:00Z",
        country="US",
        currency="USD",
        securities=[
            portfolio_verification.VerifiedSecurityQuote(
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
        patch.object(
            portfolio_verification.cache,
            "get",
            new_callable=AsyncMock,
            return_value=expected.model_dump(mode="json"),
        ),
        patch.object(portfolio_verification.services_stock, "resolve_symbol") as mock_resolve,
    ):
        result = asyncio.run(
            portfolio_verification.verify_security_quotes(
                ["NASDAQ:AAPL"],
                country="US",
            )
        )

    assert result == expected
    mock_resolve.assert_not_called()


def test_candidate_verification_normalizes_and_rejects_wrong_currency():
    with patch.object(
        portfolio_verification.services_stock,
        "resolve_symbol",
        side_effect=[
            _resolved_symbol(
                symbol="SGOV",
                price=None,
                exchange="NYSE",
                normalized_symbol="NYSE:SGOV",
            ),
            _resolved_symbol(
                symbol="CBA.AX",
                price=150,
                currency="AUD",
                exchange="ASX",
                normalized_symbol="ASX:CBA",
            ),
        ],
    ):
        result = portfolio_verification.verify_candidate_identities(
            ["NASDAQ:SGOV", "ASX:CBA"],
            country="US",
            expected_currency="USD",
        )

    assert [identity.ticker for identity in result.identities] == ["NYSE:SGOV"]
    assert result.identities[0].requested_ticker == "NASDAQ:SGOV"
    assert result.rejected_tickers == ("ASX:CBA",)


def test_candidate_verification_rejects_noncanonical_provider_identity():
    with patch.object(
        portfolio_verification.services_stock,
        "resolve_symbol",
        return_value=_resolved_symbol(
            symbol="GOVT",
            price=23.45,
            exchange="CBOE US",
            normalized_symbol="CBOE US:GOVT",
        ),
    ):
        result = portfolio_verification.verify_candidate_identities(
            ["NYSE:GOVT"],
            country="US",
            expected_currency="USD",
        )

    assert result.identities == ()
    assert result.rejected_tickers == ("NYSE:GOVT",)


def test_portfolio_verification_preserves_client_price_fallback():
    position = models_portfolio.PortfolioHolding(
        ticker="NASDAQ:AAPL",
        num_shares=10,
        avg_price=150,
        market_price=200,
    )
    with patch.object(
        portfolio_verification.services_stock,
        "resolve_symbol",
        return_value=_resolved_symbol(symbol="AAPL", price=None),
    ):
        result = portfolio_verification._build_verified_portfolio(
            [position],
            country="US",
        )

    assert result.holdings[0].market_price == 200
    assert result.holdings[0].price_source == "Client"
    assert "client-supplied market price" in result.data_gaps[0]
