import pytest
from pydantic import ValidationError

from app.models import event as models_event
from app.models import events_listings as models_events_listings


def _outlook_data() -> dict[str, object]:
    return {
        "assessment_type": "Forecast",
        "period_end": "2026-09-01",
        "direction": "Up",
        "expected_price_min": 1.1,
        "expected_price_max": 1.3,
        "expected_return_min_pct": 10,
        "expected_return_max_pct": 30,
        "confidence": 70,
        "rationale": "Supported by verified demand.",
        "key_drivers": ["Demand"],
        "risk_factors": ["Volatility"],
        "assumptions": ["Market conditions remain stable"],
        "data_gaps": [],
        "reference_ids": ["asx-source"],
    }


def test_event_base_requires_timestamp_str():
    with pytest.raises(ValidationError, match="timestamp_str"):
        models_event.UpcomingEarningsEvent(symbol="NASDAQ:AAPL")


def test_listing_event_is_market_neutral_and_uses_positive_monetary_fields():
    event = models_events_listings.ListingEvent(
        symbol="NASDAQ:ABCD",
        exchange="NASDAQ",
        timestamp_str="2026-09-01",
        issue_price=1.5,
        currency="USD",
        capital_to_raise=10_000_000,
    )

    assert event.symbol == "NASDAQ:ABCD"
    assert event.currency == "USD"
    assert event.issue_price == 1.5
    assert event.capital_to_raise == 10_000_000
    assert event.model_dump()["timestamp_str"] == "2026-09-01"
    assert "date" not in event.model_dump()
    assert "price" not in event.model_dump()
    assert "capital" not in event.model_dump()


def test_listing_event_retains_unavailable_monetary_fields_as_none():
    event = models_events_listings.ListingEvent(
        symbol="ASX:EF2",
        exchange="ASX",
        timestamp_str="2026-08-20",
        issue_price=None,
        currency="AUD",
        capital_to_raise=None,
    )

    assert event.issue_price is None
    assert event.capital_to_raise is None


def test_listing_event_requires_whole_unit_capital_to_raise():
    with pytest.raises(ValidationError):
        models_events_listings.ListingEvent(
            symbol="ASX:EF2",
            exchange="ASX",
            timestamp_str="2026-08-20",
            issue_price=None,
            currency="AUD",
            capital_to_raise=1.5,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("issue_price", 0),
        ("issue_price", -1),
        ("capital_to_raise", 0),
        ("capital_to_raise", -1),
    ],
)
def test_listing_event_rejects_non_positive_monetary_fields(field, value):
    data = {
        "symbol": "NASDAQ:ABCD",
        "timestamp_str": "2026-09-01",
        "issue_price": 1.5,
        "currency": "USD",
        "capital_to_raise": 10_000_000,
    }
    data[field] = value

    with pytest.raises(ValidationError):
        models_events_listings.ListingEvent.model_validate(data)


def test_listing_event_requires_explicit_currency():
    with pytest.raises(ValidationError, match="currency"):
        models_events_listings.ListingEvent(
            symbol="NASDAQ:ABCD",
            timestamp_str="2026-09-01",
            issue_price=1.5,
            capital_to_raise=10_000_000,
        )


def test_listing_analysis_symbol_schema_has_no_exchange_constraint():
    symbol_schema = models_events_listings.ListingAnalysis.model_json_schema()["properties"]["symbol"]

    assert "pattern" not in symbol_schema


def test_listing_period_outlook_rejects_reversed_ranges():
    data = _outlook_data()
    data["expected_price_min"] = 2
    data["expected_price_max"] = 1

    with pytest.raises(ValidationError, match="expected_price_min must not exceed expected_price_max"):
        models_events_listings.ListingPeriodOutlook.model_validate(data)


def test_listing_outlook_requires_all_four_periods():
    period = _outlook_data()

    with pytest.raises(ValidationError):
        models_events_listings.ListingOutlook.model_validate(
            {
                "ipo_day": period,
                "first_week": period,
                "first_two_weeks": period,
            }
        )
