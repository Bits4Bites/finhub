import pytest
from pydantic import ValidationError

from app.models import portfolio as models_portfolio


def test_portfolio_holding_normalizes_ticker_and_tags():
    holding = models_portfolio.PortfolioHolding(
        ticker=" nasdaq:aapl ",
        tags=" growth ",
    )

    assert holding.ticker == "NASDAQ:AAPL"
    assert holding.tags == "growth"


def test_portfolio_holding_rejects_long_ticker():
    with pytest.raises(ValidationError):
        models_portfolio.PortfolioHolding(ticker="A" * 33)


def test_portfolio_holding_rejects_negative_and_non_finite_values():
    with pytest.raises(ValidationError):
        models_portfolio.PortfolioHolding(
            ticker="AAPL",
            num_shares=-1,
            avg_price=float("nan"),
        )


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("ticker", "A" * 33),
        ("company_name", "A" * 201),
        ("exchange", "A" * 33),
        ("currency", "US"),
        ("tags", "A" * 501),
    ],
)
def test_verified_holding_enforces_shared_field_lengths(field_name, value):
    data = {
        "ticker": "NASDAQ:AAPL",
        "company_name": "Apple Inc.",
        "exchange": "NASDAQ",
        "currency": "USD",
        "num_shares": 10,
        "avg_price": 150,
        "market_price": 200,
        "price_source": "MarketData",
        "market_value": 2000,
        "current_allocation": 1,
        "target_allocation": 0.6,
        "allocation_drift": 0.4,
        "unrealized_profit_loss": 500,
        "tags": "growth",
    }
    data[field_name] = value

    with pytest.raises(ValidationError):
        models_portfolio.PortfolioVerifiedHolding.model_validate(data)
