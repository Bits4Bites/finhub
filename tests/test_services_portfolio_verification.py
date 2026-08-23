import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.models import portfolio as models_portfolio
from app.services import portfolio_verification


def _ticker(
    *,
    symbol: str,
    price: float | None,
    currency: str = "USD",
) -> MagicMock:
    ticker = MagicMock()
    ticker.info = {
        "quoteType": "EQUITY",
        "symbol": symbol,
        "fullExchangeName": "NASDAQ",
        "currency": currency,
        "regularMarketPrice": price,
        "longName": f"{symbol} Incorporated",
    }
    return ticker


def test_build_verified_security_quotes_uses_market_data_without_holdings():
    with patch.object(
        portfolio_verification.yf,
        "Ticker",
        side_effect=[
            _ticker(symbol="AAPL", price=200),
            _ticker(symbol="MSFT", price=400),
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


def test_verify_security_quotes_returns_cached_snapshot_without_market_call():
    expected = portfolio_verification.VerifiedSecurityQuotes(
        as_of="2026-08-21T00:00:00Z",
        country="US",
        currency="USD",
        securities=[
            portfolio_verification.VerifiedSecurityQuote(
                ticker="NASDAQ:AAPL",
                company_name="Apple Inc.",
                exchange="NASDAQ",
                currency="USD",
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
        patch.object(portfolio_verification.yf, "Ticker") as mock_ticker,
    ):
        result = asyncio.run(
            portfolio_verification.verify_security_quotes(
                ["NASDAQ:AAPL"],
                country="US",
            )
        )

    assert result == expected
    mock_ticker.assert_not_called()


def test_portfolio_verification_preserves_client_price_fallback():
    position = models_portfolio.PortfolioHolding(
        ticker="NASDAQ:AAPL",
        num_shares=10,
        avg_price=150,
        market_price=200,
    )
    with patch.object(
        portfolio_verification.yf,
        "Ticker",
        return_value=_ticker(symbol="AAPL", price=None),
    ):
        result = portfolio_verification._build_verified_portfolio(
            [position],
            country="US",
        )

    assert result.holdings[0].market_price == 200
    assert result.holdings[0].price_source == "Client"
    assert "client-supplied market price" in result.data_gaps[0]
