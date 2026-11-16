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


def test_normalize_canonical_ticker_trims_uppercases_and_normalizes_alias():
    assert models_portfolio.normalize_canonical_ticker(" nysearca:sgov ") == "NYSE:SGOV"


def test_normalize_canonical_ticker_preserves_unknown_exchange():
    assert models_portfolio.normalize_canonical_ticker(" custom:abc ") == "CUSTOM:ABC"


def test_normalize_canonical_ticker_returns_valid_canonical_output():
    assert models_portfolio.normalize_canonical_ticker(" asx:cba ") == "ASX:CBA"


@pytest.mark.parametrize(
    "ticker",
    [
        pytest.param("AAPL", id="missing-exchange"),
        pytest.param(":AAPL", id="empty-exchange"),
        pytest.param("NASDAQ:", id="empty-code"),
        pytest.param("NASDAQ:AAPL:US", id="extra-colon"),
        pytest.param("NASDAQ:AA PL", id="embedded-whitespace"),
    ],
)
def test_normalize_canonical_ticker_rejects_invalid_strings(ticker):
    with pytest.raises(ValueError):
        models_portfolio.normalize_canonical_ticker(ticker)


def test_normalize_canonical_ticker_passes_non_strings_to_model_validation():
    value = object()

    assert models_portfolio.normalize_canonical_ticker(value) is value


def test_portfolio_holding_rejects_long_canonical_ticker_by_length():
    long_ticker = f"UNKNOWN:{'A' * 25}"
    assert len(long_ticker) == 33

    with pytest.raises(ValidationError) as exc_info:
        models_portfolio.PortfolioHolding(ticker=long_ticker)

    assert any(error["loc"] == ("ticker",) and error["type"] == "string_too_long" for error in exc_info.value.errors())


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
        ("ticker", f"UNKNOWN:{'A' * 25}"),
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
