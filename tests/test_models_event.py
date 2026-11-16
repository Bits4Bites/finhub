import json

import pydantic
import pytest

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


def _analysis_section() -> dict[str, object]:
    return {
        "facts": [
            {
                "text": "The issuer published verified listing information.",
                "reference_ids": ["asx-source"],
            }
        ],
        "data_gaps": [],
        "reference_ids": ["asx-source"],
        "summary": "Verified listing information supports the assessment.",
        "data_quality": "High",
        "assumptions": [],
    }


def _listing_analysis() -> models_events_listings.ListingAnalysis:
    section = _analysis_section()
    return models_events_listings.ListingAnalysis.model_validate(
        {
            "symbol": "ASX:EF2",
            "as_of": "2026-08-19T23:00:00Z",
            "listing_status": "Upcoming",
            "overall_data_quality": "High",
            "executive_summary": section,
            "overall_stance": "Neutral",
            "overall_confidence": 70,
            "offer": {
                **section,
                "issue_price_assessment": "The offer price is supported by available evidence.",
                "capital_raise_assessment": "The raise is sufficient for the stated uses.",
                "underwriting_assessment": "Underwriting support reduces execution risk.",
                "use_of_funds": ["Fund expansion"],
                "dilution_and_escrow": None,
            },
            "business": {
                **section,
                "business_model": "The issuer provides specialist software.",
                "revenue_sources": ["Subscriptions"],
                "competitive_position": "The issuer serves a defined market niche.",
                "sector_context": "Sector demand remains stable.",
            },
            "financials": {
                **section,
                "historical_performance": "Revenue has grown from a small base.",
                "profitability_and_cash_flow": "Cash flow remains investment dependent.",
                "balance_sheet_and_funding": "Listing proceeds improve funding capacity.",
                "forecast_quality": "Forecasts are supported by disclosed assumptions.",
            },
            "valuation": {
                **section,
                "valuation_view": "The offer valuation is balanced.",
                "implied_market_cap": 25_000_000,
                "peer_comparison": "The valuation is within the peer range.",
                "sensitivity": "Execution and growth assumptions drive valuation.",
            },
            "governance": {
                **section,
                "board_and_management": "Management has relevant operating experience.",
                "ownership_and_escrow": "Escrow aligns major holders after listing.",
                "governance_concerns": [],
            },
            "risks_and_catalysts": {
                **section,
                "risks": [
                    {
                        "title": "Execution",
                        "description": "Growth depends on successful execution.",
                        "likelihood": "Medium",
                        "horizon": "Longer Term",
                        "reference_ids": ["asx-source"],
                        "severity": "Medium",
                    }
                ],
                "catalysts": [
                    {
                        "title": "Expansion",
                        "description": "Listing proceeds may accelerate expansion.",
                        "likelihood": "Medium",
                        "horizon": "Longer Term",
                        "reference_ids": ["asx-source"],
                    }
                ],
            },
            "outlook": {
                "ipo_day": _outlook_data(),
                "first_week": _outlook_data(),
                "first_two_weeks": _outlook_data(),
                "first_month": _outlook_data(),
            },
            "references": [
                {
                    "id": "asx-source",
                    "title": "Listing prospectus",
                    "publisher": "ASX",
                    "source_type": "Exchange",
                    "published_at": "2026-08-18T00:00:00Z",
                    "accessed_at": "2026-08-19T23:00:00Z",
                    "url": "https://example.com/listing-prospectus",
                    "is_verified": True,
                }
            ],
        }
    )


def _listing_event_data() -> dict[str, object]:
    return {
        "symbol": "ASX:EF2",
        "exchange": "ASX",
        "timestamp_str": "2026-08-20",
        "issue_price": 1.5,
        "issue_price_upper": None,
        "currency": "AUD",
        "capital_to_raise": 10_000_000,
        "analysis_status": "NotStarted",
        "analysis_error": None,
        "analysis": None,
    }


def test_event_base_requires_timestamp_str():
    with pytest.raises(pydantic.ValidationError):
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
    with pytest.raises(pydantic.ValidationError):
        parser(json.dumps([record]), {"sym": "FALLBACK"})


def test_listing_event_normalizes_canonical_symbol_and_serializes_monetary_fields():
    data = _listing_event_data()
    data["symbol"] = " asx:ef2 "
    data["currency"] = " aud "

    event = models_events_listings.ListingEvent.model_validate(data)

    serialized = event.model_dump(mode="json")
    assert serialized["symbol"] == "ASX:EF2"
    assert serialized["currency"] == "AUD"
    assert serialized["issue_price"] == 1.5
    assert serialized["capital_to_raise"] == 10_000_000
    assert serialized["timestamp_str"] == "2026-08-20"


def test_listing_event_rejects_symbol_without_exchange():
    data = _listing_event_data()
    data["symbol"] = "EF2"

    with pytest.raises(pydantic.ValidationError):
        models_events_listings.ListingEvent.model_validate(data)


def test_listing_event_retains_unavailable_monetary_fields_as_none():
    data = _listing_event_data()
    data["issue_price"] = None
    data["capital_to_raise"] = None

    event = models_events_listings.ListingEvent.model_validate(data)

    assert event.issue_price is None
    assert event.capital_to_raise is None


def test_listing_event_requires_whole_unit_capital_to_raise():
    data = _listing_event_data()
    data["capital_to_raise"] = 1.5

    with pytest.raises(pydantic.ValidationError):
        models_events_listings.ListingEvent.model_validate(data)


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
    data = _listing_event_data()
    data[field] = value

    with pytest.raises(pydantic.ValidationError):
        models_events_listings.ListingEvent.model_validate(data)


def test_listing_event_rejects_reversed_issue_price_range():
    data = _listing_event_data()
    data["issue_price"] = 2.0
    data["issue_price_upper"] = 1.5

    with pytest.raises(pydantic.ValidationError):
        models_events_listings.ListingEvent.model_validate(data)


def test_listing_event_requires_explicit_currency():
    data = _listing_event_data()
    del data["currency"]

    with pytest.raises(pydantic.ValidationError):
        models_events_listings.ListingEvent.model_validate(data)


def test_listing_event_rejects_non_alpha_currency_code():
    data = _listing_event_data()
    data["currency"] = "A$D"

    with pytest.raises(pydantic.ValidationError):
        models_events_listings.ListingEvent.model_validate(data)


def test_listing_analysis_referenced_source_ids_returns_nested_citations():
    analysis = _listing_analysis()

    assert analysis.referenced_source_ids() == {analysis.references[0].id}


def test_listing_analysis_requires_canonical_exchange_qualified_symbol():
    data = _listing_analysis().model_dump(mode="python")
    data["symbol"] = "EF2"

    with pytest.raises(pydantic.ValidationError):
        models_events_listings.ListingAnalysis.model_validate(data)


def test_listing_event_accepts_completed_analysis():
    data = _listing_event_data()
    data["analysis_status"] = "Completed"
    data["analysis"] = _listing_analysis().model_dump(mode="python")

    event = models_events_listings.ListingEvent.model_validate(data)

    serialized = event.model_dump(mode="json")
    assert serialized["analysis_status"] == "Completed"
    assert serialized["analysis"]["symbol"] == serialized["symbol"]
    assert serialized["analysis_error"] is None


def test_listing_event_accepts_failed_status_with_nonblank_error():
    data = _listing_event_data()
    data["analysis_status"] = "Failed"
    data["analysis_error"] = " AI listing analysis failed "

    event = models_events_listings.ListingEvent.model_validate(data)

    assert event.analysis is None
    assert event.model_dump(mode="json")["analysis_error"] == "AI listing analysis failed"


@pytest.mark.parametrize(
    ("status", "analysis", "analysis_error"),
    [
        ("Completed", None, None),
        ("Failed", None, " "),
        ("Failed", _listing_analysis(), "Analysis failed"),
        ("NotStarted", _listing_analysis(), None),
        ("Skipped", None, "Analysis was skipped"),
    ],
    ids=[
        "completed-without-analysis",
        "failed-without-error",
        "failed-with-analysis",
        "not-started-with-analysis",
        "skipped-with-error",
    ],
)
def test_listing_event_rejects_invalid_status_analysis_matrix(status, analysis, analysis_error):
    data = _listing_event_data()
    data["analysis_status"] = status
    data["analysis"] = analysis
    data["analysis_error"] = analysis_error

    with pytest.raises(pydantic.ValidationError):
        models_events_listings.ListingEvent.model_validate(data)


def test_listing_event_rejects_completed_analysis_for_another_symbol():
    analysis_data = _listing_analysis().model_dump(mode="python")
    analysis_data["symbol"] = "ASX:OTHER"
    data = _listing_event_data()
    data["analysis_status"] = "Completed"
    data["analysis"] = analysis_data

    with pytest.raises(pydantic.ValidationError):
        models_events_listings.ListingEvent.model_validate(data)


def test_listing_period_outlook_rejects_reversed_ranges():
    data = _outlook_data()
    data["expected_price_min"] = 2
    data["expected_price_max"] = 1

    with pytest.raises(pydantic.ValidationError):
        models_events_listings.ListingPeriodOutlook.model_validate(data)


def test_listing_outlook_accepts_and_serializes_all_four_periods():
    period = _outlook_data()

    outlook = models_events_listings.ListingOutlook.model_validate(
        {
            "ipo_day": period,
            "first_week": period,
            "first_two_weeks": period,
            "first_month": period,
        }
    )

    assert set(outlook.model_dump(mode="json")) == {
        "ipo_day",
        "first_week",
        "first_two_weeks",
        "first_month",
    }


def test_listing_outlook_rejects_missing_period():
    period = _outlook_data()

    with pytest.raises(pydantic.ValidationError):
        models_events_listings.ListingOutlook.model_validate(
            {
                "ipo_day": period,
                "first_week": period,
                "first_two_weeks": period,
            }
        )
