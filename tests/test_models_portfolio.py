import math

import pydantic
import pytest

from app.models import portfolio as models_portfolio


def _verified_holding_data() -> dict[str, object]:
    return {
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


def test_portfolio_holding_normalizes_and_serializes_ticker_and_tags():
    holding = models_portfolio.PortfolioHolding(
        ticker=" nasdaq:aapl ",
        tags=" growth ",
    )

    serialized = holding.model_dump(mode="json")
    assert serialized["ticker"] == "NASDAQ:AAPL"
    assert serialized["tags"] == "growth"


def test_normalize_canonical_ticker_normalizes_alias_and_case():
    assert models_portfolio.normalize_canonical_ticker(" nysearca:sgov ") == "NYSE:SGOV"


def test_normalize_canonical_ticker_preserves_unknown_exchange():
    assert models_portfolio.normalize_canonical_ticker(" custom:abc ") == "CUSTOM:ABC"


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
def test_normalize_canonical_ticker_rejects_noncanonical_strings(ticker):
    with pytest.raises(ValueError):
        models_portfolio.normalize_canonical_ticker(ticker)


def test_normalize_canonical_ticker_returns_non_strings_for_field_validation():
    value = object()

    assert models_portfolio.normalize_canonical_ticker(value) is value


def test_portfolio_holding_rejects_ticker_over_documented_length():
    long_ticker = f"UNKNOWN:{'A' * 25}"

    with pytest.raises(pydantic.ValidationError):
        models_portfolio.PortfolioHolding(ticker=long_ticker)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("ticker", "AA PL"),
        ("num_shares", -1),
        ("avg_price", math.nan),
        ("market_price", 0),
        ("target_allocation", 1.1),
    ],
)
def test_portfolio_holding_rejects_invalid_documented_value(field_name, value):
    data = {
        "ticker": "AAPL",
        "num_shares": 1,
        "avg_price": 10,
        "market_price": 11,
        "target_allocation": 0.5,
    }
    data[field_name] = value

    with pytest.raises(pydantic.ValidationError):
        models_portfolio.PortfolioHolding.model_validate(data)


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (
            {
                "budget_type": "NotProvided",
                "is_inferred": False,
                "amount": None,
                "currency": None,
                "frequency": None,
                "source_text": None,
            },
            {
                "budget_type": "NotProvided",
                "is_inferred": False,
                "amount": None,
                "currency": None,
                "frequency": None,
                "source_text": None,
            },
        ),
        (
            {
                "budget_type": "Total",
                "is_inferred": False,
                "amount": 1000,
                "currency": " usd ",
                "frequency": None,
                "source_text": "Total budget USD 1000",
            },
            {
                "budget_type": "Total",
                "is_inferred": False,
                "amount": 1000.0,
                "currency": "USD",
                "frequency": None,
                "source_text": "Total budget USD 1000",
            },
        ),
        (
            {
                "budget_type": "Recurring",
                "is_inferred": False,
                "amount": 250,
                "currency": "USD",
                "frequency": "Monthly",
                "source_text": "Monthly contribution USD 250",
            },
            {
                "budget_type": "Recurring",
                "is_inferred": False,
                "amount": 250.0,
                "currency": "USD",
                "frequency": "Monthly",
                "source_text": "Monthly contribution USD 250",
            },
        ),
        (
            {
                "budget_type": "Recurring",
                "is_inferred": True,
                "amount": 200,
                "currency": "USD",
                "frequency": None,
                "source_text": "Application-inferred next-iteration budget.",
            },
            {
                "budget_type": "Recurring",
                "is_inferred": True,
                "amount": 200.0,
                "currency": "USD",
                "frequency": None,
                "source_text": "Application-inferred next-iteration budget.",
            },
        ),
    ],
    ids=["not-provided", "total", "recurring", "inferred-recurring"],
)
def test_portfolio_budget_accepts_and_serializes_documented_matrix(payload, expected):
    budget = models_portfolio.PortfolioBudget.model_validate(payload)

    assert budget.model_dump(mode="json") == expected


@pytest.mark.parametrize(
    "payload",
    [
        {
            "budget_type": "NotProvided",
            "is_inferred": False,
            "amount": 1,
            "currency": None,
            "frequency": None,
            "source_text": None,
        },
        {
            "budget_type": "Total",
            "is_inferred": False,
            "amount": 1000,
            "currency": "USD",
            "frequency": "Monthly",
            "source_text": "Total budget USD 1000",
        },
        {
            "budget_type": "Recurring",
            "is_inferred": False,
            "amount": 250,
            "currency": "USD",
            "frequency": None,
            "source_text": "Monthly contribution USD 250",
        },
        {
            "budget_type": "Recurring",
            "is_inferred": True,
            "amount": 200,
            "currency": "USD",
            "frequency": "Monthly",
            "source_text": "Application-inferred next-iteration budget.",
        },
    ],
    ids=["details-without-budget", "total-with-frequency", "recurring-without-frequency", "inferred-with-frequency"],
)
def test_portfolio_budget_rejects_invalid_documented_matrix(payload):
    with pytest.raises(pydantic.ValidationError):
        models_portfolio.PortfolioBudget.model_validate(payload)


def test_portfolio_budget_rejects_non_alpha_currency_code():
    with pytest.raises(pydantic.ValidationError):
        models_portfolio.PortfolioBudget(
            budget_type="Total",
            is_inferred=False,
            amount=1000,
            currency="U$D",
            frequency=None,
            source_text="Total budget U$D 1000",
        )


def test_verified_holding_requires_canonical_exchange_qualified_ticker():
    data = _verified_holding_data()
    data["ticker"] = "AAPL"

    with pytest.raises(pydantic.ValidationError):
        models_portfolio.PortfolioVerifiedHolding.model_validate(data)


def test_verified_holding_normalizes_exchange_alias_and_currency():
    data = _verified_holding_data()
    data.update(
        {
            "ticker": " nysearca:sgov ",
            "exchange": " nysearca ",
            "currency": " usd ",
        }
    )

    holding = models_portfolio.PortfolioVerifiedHolding.model_validate(data)

    assert holding.ticker == "NYSE:SGOV"
    assert holding.exchange == "NYSE"
    assert holding.currency == "USD"


def test_verified_holding_rejects_exchange_that_does_not_match_ticker():
    data = _verified_holding_data()
    data["exchange"] = "NYSE"

    with pytest.raises(pydantic.ValidationError):
        models_portfolio.PortfolioVerifiedHolding.model_validate(data)


def test_verified_holding_preserves_service_supplied_calculated_fields():
    data = _verified_holding_data()
    data.update(
        {
            "market_value": 1234,
            "current_allocation": 0.42,
            "allocation_drift": -0.18,
            "unrealized_profit_loss": -25,
        }
    )

    holding = models_portfolio.PortfolioVerifiedHolding.model_validate(data)

    serialized = holding.model_dump(mode="json")
    assert serialized["market_value"] == 1234
    assert serialized["current_allocation"] == 0.42
    assert serialized["allocation_drift"] == -0.18
    assert serialized["unrealized_profit_loss"] == -25


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("ticker", f"UNKNOWN:{'A' * 25}"),
        ("company_name", "A" * 201),
        ("exchange", "A" * 33),
        ("currency", "US"),
        ("currency", "U$D"),
        ("tags", "A" * 501),
    ],
)
def test_verified_holding_rejects_field_over_documented_limits(field_name, value):
    data = _verified_holding_data()
    data[field_name] = value

    with pytest.raises(pydantic.ValidationError):
        models_portfolio.PortfolioVerifiedHolding.model_validate(data)
