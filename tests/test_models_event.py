import json

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


def test_parse_dividend_events_accepts_fenced_array_in_order_and_uses_utc_midnight():
    events = models_event.parse_upcoming_dividend_events_from_json(
        """```json
[
  {
    "sym": "AAA",
    "exchange": "ASX",
    "corp": "Alpha Ltd",
    "date": "1970-01-01",
    "pdate": "1970-01-10",
    "cat": "distribution",
    "src": "Exchange feed",
    "link": "https://example.com/alpha",
    "status": "declared",
    "amount": 1.25,
    "yield": 0.04,
    "currency": "AUD"
  },
  {
    "sym": "BBB",
    "date": "1970-01-02",
    "pdate": null
  }
]
```"""
    )

    assert [event.symbol for event in events] == ["AAA", "BBB"]
    assert [event.timestamp for event in events] == [0, 86_400]
    assert events[0].event_category == "distribution"
    assert events[0].company_name == "Alpha Ltd"
    assert events[0].payment_date == "1970-01-10"
    assert events[0].link == "https://example.com/alpha"
    assert events[0].amount == 1.25
    assert events[0].dividend_yield == 0.04
    assert events[1].event_category == "dividend"
    assert events[1].payment_date is None
    assert events[1].exchange == ""
    assert events[1].company_name == ""
    assert events[1].status == ""
    assert events[1].amount == 0.0
    assert events[1].dividend_yield == 0.0
    assert events[1].currency == ""


def test_parse_dividend_events_uses_source_key_defaults_for_missing_values():
    event = models_event.parse_upcoming_dividend_events_from_json(
        "[{}]",
        {
            "sym": "CBA",
            "exchange": "ASX",
            "corp": "Commonwealth Bank",
            "date": "2026-01-05",
            "pdate": None,
            "cat": "distribution",
            "src": "ASX",
            "link": "https://example.com/cba",
            "status": "declared",
            "amount": 1.2,
            "yield": 0.03,
            "currency": "AUD",
        },
    )[0]

    assert event.symbol == "CBA"
    assert event.exchange == "ASX"
    assert event.company_name == "Commonwealth Bank"
    assert event.timestamp_str == "2026-01-05"
    assert event.payment_date is None
    assert event.event_category == "distribution"
    assert event.source_name == "ASX"
    assert event.status == "declared"
    assert event.amount == 1.2
    assert event.dividend_yield == 0.03
    assert event.currency == "AUD"


def test_parse_earnings_events_accepts_fenced_array_in_order_and_uses_defaults():
    records = [
        {
            "sym": "AAPL",
            "date": "1970-01-02",
            "link": "https://example.com/aapl",
            "status": None,
        },
        {"sym": "MSFT", "date": "1970-01-03", "exchange": "NYSE", "src": "SEC"},
    ]

    events = models_event.parse_upcoming_earnings_events_from_json(
        f"```json\n{json.dumps(records)}\n```",
        {
            "exchange": "NASDAQ",
            "src": "TipRanks",
            "status": "estimated",
            "report_period": "FY2027",
        },
    )

    assert [event.symbol for event in events] == ["AAPL", "MSFT"]
    assert [event.timestamp for event in events] == [86_400, 172_800]
    assert all(event.event_category == "earnings" for event in events)
    assert events[0].exchange == "NASDAQ"
    assert events[0].company_name == ""
    assert events[0].source_name == "TipRanks"
    assert events[0].link == "https://example.com/aapl"
    assert events[0].status is None
    assert events[0].report_period == "FY2027"
    assert events[1].exchange == "NYSE"
    assert events[1].source_name == "SEC"
    assert events[1].status == "estimated"


@pytest.mark.parametrize(
    "parser",
    [
        models_event.parse_upcoming_dividend_events_from_json,
        models_event.parse_upcoming_earnings_events_from_json,
    ],
    ids=["dividend", "earnings"],
)
def test_event_parsers_return_empty_list_for_empty_array(parser):
    assert parser("[]") == []


@pytest.mark.parametrize(
    "parser",
    [
        models_event.parse_upcoming_dividend_events_from_json,
        models_event.parse_upcoming_earnings_events_from_json,
    ],
    ids=["dividend", "earnings"],
)
def test_event_parsers_reject_non_array_top_level_values(parser):
    with pytest.raises(ValueError):
        parser('{"sym": "AAA"}')


@pytest.mark.parametrize(
    "parser",
    [
        models_event.parse_upcoming_dividend_events_from_json,
        models_event.parse_upcoming_earnings_events_from_json,
    ],
    ids=["dividend", "earnings"],
)
def test_event_parsers_reject_non_object_records(parser):
    with pytest.raises(TypeError):
        parser("[null]")


@pytest.mark.parametrize(
    "parser",
    [
        models_event.parse_upcoming_dividend_events_from_json,
        models_event.parse_upcoming_earnings_events_from_json,
    ],
    ids=["dividend", "earnings"],
)
def test_event_parsers_propagate_json_errors(parser):
    with pytest.raises(json.JSONDecodeError):
        parser("[")


@pytest.mark.parametrize(
    ("parser", "record"),
    [
        (
            models_event.parse_upcoming_dividend_events_from_json,
            {"sym": "AAA", "date": "2026/01/01", "pdate": None},
        ),
        (
            models_event.parse_upcoming_earnings_events_from_json,
            {"sym": "AAA", "date": "2026/01/01"},
        ),
    ],
    ids=["dividend", "earnings"],
)
def test_event_parsers_reject_dates_outside_yyyy_mm_dd_format(parser, record):
    with pytest.raises(ValueError):
        parser(json.dumps([record]))


@pytest.mark.parametrize(
    ("parser", "record"),
    [
        (
            models_event.parse_upcoming_dividend_events_from_json,
            {"sym": "AAA", "date": "2026-1-1", "pdate": None},
        ),
        (
            models_event.parse_upcoming_earnings_events_from_json,
            {"sym": "AAA", "date": "2026-1-1"},
        ),
    ],
    ids=["dividend", "earnings"],
)
def test_event_parsers_reject_non_zero_padded_dates(parser, record):
    with pytest.raises(ValueError):
        parser(json.dumps([record]))


@pytest.mark.parametrize(
    ("parser", "record"),
    [
        (
            models_event.parse_upcoming_dividend_events_from_json,
            {"sym": "AAA", "date": "2026-02-30", "pdate": None},
        ),
        (
            models_event.parse_upcoming_earnings_events_from_json,
            {"sym": "AAA", "date": "2026-02-30"},
        ),
    ],
    ids=["dividend", "earnings"],
)
def test_event_parsers_reject_invalid_calendar_dates(parser, record):
    with pytest.raises(ValueError):
        parser(json.dumps([record]))


@pytest.mark.parametrize(
    ("parser", "record"),
    [
        (
            models_event.parse_upcoming_dividend_events_from_json,
            {"sym": None, "date": "2026-01-01", "pdate": None},
        ),
        (
            models_event.parse_upcoming_earnings_events_from_json,
            {"sym": None, "date": "2026-01-01"},
        ),
    ],
    ids=["dividend", "earnings"],
)
def test_event_parsers_preserve_explicit_nulls_for_model_validation(parser, record):
    with pytest.raises(ValidationError, match="symbol"):
        parser(json.dumps([record]), {"sym": "FALLBACK"})


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
        ("issue_price_upper", 0),
        ("issue_price_upper", -1),
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


def test_listing_event_rejects_reversed_issue_price_range():
    with pytest.raises(ValidationError, match="issue_price must not exceed issue_price_upper"):
        models_events_listings.ListingEvent(
            symbol="NASDAQ:ABCD",
            timestamp_str="2026-09-01",
            issue_price=2.0,
            issue_price_upper=1.5,
            currency="USD",
            capital_to_raise=None,
        )


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
