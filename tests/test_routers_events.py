from unittest import mock

import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app
from app.models import events_div as models_dividends
from app.models import events_earnings as models_earnings
from app.models import events_listings as models_events_listings
from app.routers import events_div as router_events_div

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolate_event_routes(monkeypatch):
    monkeypatch.setattr(config.settings_finhub_proxy, "proxy_mode", "None")
    monkeypatch.setattr(config.settings_finhub_proxy, "url_web_crawl_node", "")
    monkeypatch.setattr(config.settings_finhub_proxy, "url_ai_task_node", "")
    monkeypatch.setattr(
        router_events_div.asset_utils,
        "is_in_index",
        lambda *, index, symbol: False,
    )


def _dividend_event(
    symbol: str = "ASX:ROUTEAU",
    *,
    timestamp_str: str = "2026-06-10 00:00:00+10:00",
    amount: float = 1.25,
) -> models_dividends.UpcomingDividendEvent:
    return models_dividends.UpcomingDividendEvent(
        symbol=symbol,
        exchange=symbol.split(":", 1)[0],
        company_name="Example Dividend Co",
        timestamp_str=timestamp_str,
        status="declared",
        amount=amount,
        dividend_yield=0.03,
        currency="AUD" if symbol.startswith("ASX:") else "USD",
        payment_date=None,
    )


def _earnings_event(symbol: str = "NASDAQ:ROUTEUS") -> models_earnings.UpcomingEarningsEvent:
    return models_earnings.UpcomingEarningsEvent(
        symbol=symbol,
        exchange=symbol.split(":", 1)[0],
        company_name="Example Earnings Co",
        timestamp_str="2026-08-15 00:00:00-04:00",
        status="estimated",
        report_period=None,
    )


def _listing_analysis(
    symbol: str,
    *,
    listing_status: models_events_listings.ListingStatus = "Upcoming",
) -> models_events_listings.ListingAnalysis:
    source_id = "listing-source"
    section = {
        "facts": [
            {
                "text": "The exchange published verified listing information.",
                "reference_ids": [source_id],
            }
        ],
        "data_gaps": [],
        "reference_ids": [source_id],
        "summary": "Verified listing information supports the assessment.",
        "data_quality": "High",
        "assumptions": [],
    }
    outlook = {
        "assessment_type": "Forecast",
        "period_end": "2026-12-31",
        "direction": "Flat",
        "expected_price_min": 0.20,
        "expected_price_max": 0.25,
        "expected_return_min_pct": -5,
        "expected_return_max_pct": 5,
        "confidence": 60,
        "rationale": "The verified offer terms support a neutral outlook.",
        "key_drivers": ["Offer demand"],
        "risk_factors": ["Market volatility"],
        "assumptions": [],
        "data_gaps": [],
        "reference_ids": [source_id],
    }
    return models_events_listings.ListingAnalysis.model_validate(
        {
            "symbol": symbol,
            "as_of": "2026-11-30T00:00:00Z",
            "listing_status": listing_status,
            "overall_data_quality": "High",
            "executive_summary": section,
            "overall_stance": "Neutral",
            "overall_confidence": 60,
            "offer": {
                **section,
                "issue_price_assessment": "The offer range is supported by disclosed terms.",
                "capital_raise_assessment": "The raise supports the stated listing plan.",
                "underwriting_assessment": "No material underwriting concern was identified.",
                "use_of_funds": ["Fund expansion"],
                "dilution_and_escrow": None,
            },
            "business": {
                **section,
                "business_model": "The issuer provides financial services.",
                "revenue_sources": ["Service fees"],
                "competitive_position": "The issuer serves a defined market.",
                "sector_context": "Sector conditions are stable.",
            },
            "financials": {
                **section,
                "historical_performance": "Available performance is stable.",
                "profitability_and_cash_flow": "Cash flow supports current operations.",
                "balance_sheet_and_funding": "The offer improves funding capacity.",
                "forecast_quality": "Forecasts use disclosed assumptions.",
            },
            "valuation": {
                **section,
                "valuation_view": "The offer valuation is balanced.",
                "implied_market_cap": 25_000_000,
                "peer_comparison": "The valuation is within the peer range.",
                "sensitivity": "Demand and execution drive valuation sensitivity.",
            },
            "governance": {
                **section,
                "board_and_management": "Management has relevant experience.",
                "ownership_and_escrow": "Ownership terms are disclosed.",
                "governance_concerns": [],
            },
            "risks_and_catalysts": {
                **section,
                "risks": [],
                "catalysts": [],
            },
            "outlook": {
                "ipo_day": outlook,
                "first_week": outlook,
                "first_two_weeks": outlook,
                "first_month": outlook,
            },
            "references": [
                {
                    "id": source_id,
                    "title": "Listing announcement",
                    "publisher": "ASX",
                    "source_type": "Exchange",
                    "published_at": "2026-11-29T00:00:00Z",
                    "accessed_at": "2026-11-30T00:00:00Z",
                    "url": "https://example.com/listing-announcement",
                    "is_verified": True,
                }
            ],
        }
    )


def _listing_event(
    symbol: str,
    timestamp_str: str,
    *,
    analysis_status: models_events_listings.ListingAnalysisStatus = "Skipped",
    issue_price: float | None = None,
    issue_price_upper: float | None = None,
    analysis_error: str | None = None,
    listing_status: models_events_listings.ListingStatus = "Upcoming",
) -> models_events_listings.ListingEvent:
    return models_events_listings.ListingEvent(
        symbol=symbol,
        exchange=symbol.split(":", 1)[0],
        company_name=f"{symbol} Holdings",
        timestamp_str=timestamp_str,
        issue_price=issue_price,
        issue_price_upper=issue_price_upper,
        currency="AUD" if symbol.startswith("ASX:") else "USD",
        capital_to_raise=None,
        analysis_status=analysis_status,
        analysis_error=analysis_error,
        analysis=(_listing_analysis(symbol, listing_status=listing_status) if analysis_status == "Completed" else None),
    )


def test_dividend_country_aliases_select_the_documented_market():
    async def au(index):
        return [_dividend_event("ASX:ROUTEAU")]

    async def us(index):
        return [_dividend_event("NASDAQ:ROUTEUS")]

    async def vn(index):
        return [_dividend_event("HOSE:ROUTEVN")]

    patches = [
        mock.patch(
            "app.routers.events_div.services_events_div.get_asx_upcoming_dividends_events",
            new=au,
        ),
        mock.patch(
            "app.routers.events_div.services_events_div.get_us_upcoming_dividends_events",
            new=us,
        ),
        mock.patch(
            "app.routers.events_div.services_events_div.get_vn_upcoming_dividends_events",
            new=vn,
        ),
    ]
    with patches[0], patches[1], patches[2]:
        responses = [
            client.get(
                "/events/upcoming_dividends",
                params={"country": country, "index": index},
            )
            for country, index in [
                (" Australia ", "asx200"),
                ("u.s.a.", "sp500"),
                ("vNm", "vn30"),
            ]
        ]

    assert [response.status_code for response in responses] == [200, 200, 200]
    assert [response.json()["data"][0]["symbol"] for response in responses] == [
        "ASX:ROUTEAU",
        "NASDAQ:ROUTEUS",
        "HOSE:ROUTEVN",
    ]
    assert all("analysis" not in response.json()["data"][0] for response in responses)


def test_major_index_dividend_event_includes_available_analysis(monkeypatch):
    event = _dividend_event("NASDAQ:AAPL")
    analysis = models_dividends.DividendEventMetrics(
        symbol="NASDAQ:AAPL",
        exchange="NASDAQ",
        company_name="Apple",
        timestamp_str="2026-06-10",
        price=200.0,
        div_amount=event.amount,
        div_yield=0.00625,
    )

    async def events(index):
        return [event]

    async def analyze(*, symbol, div_amount, ex_date):
        analysis_data = analysis.model_dump(mode="python")
        analysis_data.update(
            {
                "symbol": symbol,
                "div_amount": div_amount,
                "timestamp_str": ex_date,
            }
        )
        return models_dividends.DividendEventMetrics.model_validate(analysis_data)

    monkeypatch.setattr(
        router_events_div.asset_utils,
        "is_in_index",
        lambda *, index, symbol: index == "SP500" and symbol == "NASDAQ:AAPL",
    )
    with (
        mock.patch(
            "app.routers.events_div.services_events_div.get_us_upcoming_dividends_events",
            new=events,
        ),
        mock.patch(
            "app.routers.events_div.services_events_div.analyse_dividend_event",
            new=analyze,
        ),
    ):
        response = client.get(
            "/events/upcoming_dividends",
            params={"country": "US", "index": "sp500"},
        )

    assert response.status_code == 200
    returned = response.json()["data"][0]
    assert returned["analysis"]["symbol"] == "NASDAQ:AAPL"
    assert returned["analysis"]["div_amount"] == 1.25
    assert returned["analysis"]["timestamp_str"] == "2026-06-10"


@pytest.mark.parametrize("analysis_outcome", [None, RuntimeError("analysis unavailable")])
def test_unavailable_analysis_is_omitted_but_analysis_failure_is_500(monkeypatch, analysis_outcome):
    async def events(index):
        return [_dividend_event("NASDAQ:AAPL")]

    async def analyze(**kwargs):
        if isinstance(analysis_outcome, Exception):
            raise analysis_outcome
        return analysis_outcome

    monkeypatch.setattr(
        router_events_div.asset_utils,
        "is_in_index",
        lambda *, index, symbol: True,
    )
    with (
        mock.patch(
            "app.routers.events_div.services_events_div.get_us_upcoming_dividends_events",
            new=events,
        ),
        mock.patch(
            "app.routers.events_div.services_events_div.analyse_dividend_event",
            new=analyze,
        ),
    ):
        response = client.get(
            "/events/upcoming_dividends",
            params={"country": "US", "index": "SP500"},
        )

    if analysis_outcome is None:
        assert response.status_code == 200
        assert "analysis" not in response.json()["data"][0]
    else:
        assert response.status_code == 500
        assert response.json()["status"] == 500
        assert "data" not in response.json()


@pytest.mark.parametrize(
    ("country", "index"),
    [("AU", "SP500"), ("US", "ASX200"), ("Vietnam", "NOT-AN-INDEX")],
)
def test_invalid_or_cross_market_dividend_index_returns_empty_data(country, index):
    async def no_events(selected_index):
        return []

    with (
        mock.patch(
            "app.routers.events_div.services_events_div.get_asx_upcoming_dividends_events",
            new=no_events,
        ),
        mock.patch(
            "app.routers.events_div.services_events_div.get_us_upcoming_dividends_events",
            new=no_events,
        ),
        mock.patch(
            "app.routers.events_div.services_events_div.get_vn_upcoming_dividends_events",
            new=no_events,
        ),
    ):
        response = client.get(
            "/events/upcoming_dividends",
            params={"country": country, "index": index},
        )

    assert response.status_code == 200
    assert response.json()["data"] == []


@pytest.mark.parametrize("country", ["", "JP", "unknown"])
def test_unsupported_dividend_country_returns_application_501(country):
    response = client.get(
        "/events/upcoming_dividends",
        params={"country": country},
    )

    assert response.status_code == 200
    assert response.json()["status"] == 501
    assert "data" not in response.json()


def test_sync_dividend_country_is_required():
    response = client.get("/events/upcoming_dividends")

    assert response.status_code == 422


def test_earnings_country_aliases_select_the_documented_market():
    async def au(index):
        return [_earnings_event("ASX:ROUTEAU")]

    async def us(index):
        return [_earnings_event("NASDAQ:ROUTEUS")]

    with (
        mock.patch(
            "app.routers.events_earnings.services_events_earnings.get_asx_upcoming_earnings_events",
            new=au,
        ),
        mock.patch(
            "app.routers.events_earnings.services_events_earnings.get_us_upcoming_earnings_events",
            new=us,
        ),
    ):
        australia = client.get(
            "/events/upcoming_earnings",
            params={"country": " Australia ", "index": "asx200"},
        )
        united_states = client.get(
            "/events/upcoming_earnings",
            params={"country": "U.S.A.", "index": "sp500"},
        )

    assert australia.status_code == united_states.status_code == 200
    assert australia.json()["data"][0]["symbol"] == "ASX:ROUTEAU"
    assert united_states.json()["data"][0]["symbol"] == "NASDAQ:ROUTEUS"
    assert "report_period" not in united_states.json()["data"][0]


@pytest.mark.parametrize(
    ("country", "index"),
    [("AU", "SP500"), ("US", "ASX200"), ("US", "NOT-AN-INDEX")],
)
def test_invalid_or_cross_market_earnings_index_returns_empty_data(country, index):
    async def no_events(selected_index):
        return []

    with (
        mock.patch(
            "app.routers.events_earnings.services_events_earnings.get_asx_upcoming_earnings_events",
            new=no_events,
        ),
        mock.patch(
            "app.routers.events_earnings.services_events_earnings.get_us_upcoming_earnings_events",
            new=no_events,
        ),
    ):
        response = client.get(
            "/events/upcoming_earnings",
            params={"country": country, "index": index},
        )

    assert response.status_code == 200
    assert response.json()["data"] == []


@pytest.mark.parametrize("country", ["", "JP"])
def test_unsupported_earnings_country_returns_application_501(country):
    response = client.get(
        "/events/upcoming_earnings",
        params={"country": country},
    )

    assert response.status_code == 200
    assert response.json()["status"] == 501
    assert "data" not in response.json()


def test_sync_earnings_country_is_required():
    response = client.get("/events/upcoming_earnings")

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("country", "exchange", "currency"),
    [("AU", "ASX", "AUD"), ("US", "NASDAQ", "USD")],
)
def test_crawled_earnings_financial_fields_reach_sync_and_async_responses(
    deferred_task_store, country, exchange, currency
):
    html = (
        "<table><thead><tr><th>Name</th><th>Company Name</th><th>Market Cap</th>"
        "<th>EPS / Forecast</th><th>Revenue / Forecast</th></tr></thead><tbody>"
        "<tr><td>KNOWN</td><td>Known Company</td><td>$200B</td>"
        "<td>-$2.65 / N/A</td><td>$27.067B / $1.001B</td></tr></tbody></table>"
    )
    company = mock.Mock()
    company.extract_exchange_code.return_value = (exchange, "KNOWN")

    async def fetch_pages(urls, **_kwargs):
        return [html] + [None] * (len(urls) - 1)

    with (
        mock.patch(
            "app.services.crawler_earnings.crawler_core.fetch_multi_webpages_content_playwright",
            new=fetch_pages,
        ),
        mock.patch(
            "app.services.crawler_earnings.market.market_indices.revert_lookup_company",
            return_value=company,
        ),
    ):
        synchronous = client.get("/events/upcoming_earnings", params={"country": country})
        started = client.get("/events/start_upcoming_earnings_async", params={"country": country})
        task_id = started.json()["extra"]["task_id"]
        deferred_task_store.release()
        completed = client.get("/events/poll_upcoming_earnings_async", params={"task_id": task_id})
        reused = client.get("/events/start_upcoming_earnings_async", params={"country": country})

    assert started.status_code == 202
    assert synchronous.status_code == completed.status_code == reused.status_code == 200
    assert synchronous.json()["data"] == completed.json()["data"] == reused.json()["data"]
    event = synchronous.json()["data"][0]
    assert event["symbol"] == f"{exchange}:KNOWN"
    expected_financials = {
        "market_cap": 200_000_000_000,
        "eps": -2.65,
        "eps_forecast": 0.0,
        "revenue": 27_067_000_000,
        "revenue_forecast": 1_001_000_000,
        "currency": currency,
    }
    assert {field: event[field] for field in expected_financials} == expected_financials


def test_listing_country_aliases_select_the_documented_market():
    async def au():
        return [_listing_event("ASX:IPO", "2026-12-01", issue_price=2.5)]

    async def us():
        return [_listing_event("NASDAQ:IPO", "2026-12-02", issue_price=12.0)]

    with (
        mock.patch(
            "app.routers.events_listings.services_asx_listings.ai_get_asx_new_listings",
            new=au,
        ),
        mock.patch(
            "app.routers.events_listings.services_us_listings.ai_get_us_new_listings",
            new=us,
        ),
    ):
        australia = client.get("/events/new_listings", params={"country": " aUsTrAlIa "})
        united_states = client.get("/events/new_listings", params={"country": "U.S.A."})

    assert australia.status_code == united_states.status_code == 200
    assert australia.json()["data"][0]["symbol"] == "ASX:IPO"
    assert united_states.json()["data"][0]["symbol"] == "NASDAQ:IPO"


def test_listing_order_price_range_nullable_fields_and_analysis_outcomes_are_preserved():
    events = [
        _listing_event("ASX:AAA", "2026-12-01", analysis_status="Skipped"),
        _listing_event(
            "ASX:BBB",
            "2026-12-02",
            analysis_status="Completed",
            issue_price=0.20,
            issue_price_upper=0.25,
        ),
        _listing_event(
            "ASX:CCC",
            "2026-12-03",
            analysis_status="Failed",
            analysis_error="Analysis unavailable",
        ),
    ]

    async def listings():
        return events

    with mock.patch(
        "app.routers.events_listings.services_asx_listings.ai_get_asx_new_listings",
        new=listings,
    ):
        response = client.get("/events/new_listings", params={"country": "AU"})

    assert response.status_code == 200
    data = response.json()["data"]
    assert [item["symbol"] for item in data] == ["ASX:AAA", "ASX:BBB", "ASX:CCC"]
    assert [item["analysis_status"] for item in data] == ["Skipped", "Completed", "Failed"]
    assert data[1]["issue_price"] == 0.20
    assert data[1]["issue_price_upper"] == 0.25
    assert data[1]["analysis"]["symbol"] == "ASX:BBB"
    assert data[2]["analysis_error"] == "Analysis unavailable"
    assert "issue_price" not in data[2]
    assert "capital_to_raise" not in data[2]
    assert "analysis" not in data[2]


def test_completed_listing_analyses_preserve_upcoming_and_listed_statuses():
    events = [
        _listing_event(
            "ASX:LISTED",
            "2026-11-01",
            analysis_status="Completed",
            listing_status="Listed",
        ),
        _listing_event(
            "ASX:UPCOMING",
            "2026-12-01",
            analysis_status="Completed",
            listing_status="Upcoming",
        ),
    ]

    async def listings():
        return events

    with mock.patch(
        "app.routers.events_listings.services_asx_listings.ai_get_asx_new_listings",
        new=listings,
    ):
        response = client.get("/events/new_listings", params={"country": "AU"})

    assert response.status_code == 200
    assert [event["analysis"]["listing_status"] for event in response.json()["data"]] == [
        "Listed",
        "Upcoming",
    ]


@pytest.mark.parametrize("country", [None, "", "JP"])
def test_sync_listing_omitted_or_unsupported_country_returns_501(country):
    params = {} if country is None else {"country": country}

    response = client.get("/events/new_listings", params=params)

    assert response.status_code == 200
    assert response.json()["status"] == 501
    assert "data" not in response.json()


@pytest.mark.parametrize(
    ("target", "endpoint", "params"),
    [
        (
            "app.routers.events_div.services_events_div.get_asx_upcoming_dividends_events",
            "/events/upcoming_dividends",
            {"country": "AU"},
        ),
        (
            "app.routers.events_earnings.services_events_earnings.get_us_upcoming_earnings_events",
            "/events/upcoming_earnings",
            {"country": "US"},
        ),
        (
            "app.routers.events_listings.services_asx_listings.ai_get_asx_new_listings",
            "/events/new_listings",
            {"country": "AU"},
        ),
    ],
)
def test_synchronous_event_service_failures_return_public_500_envelopes(target, endpoint, params):
    async def fail(*args, **kwargs):
        raise RuntimeError("source unavailable")

    with mock.patch(target, new=fail):
        response = client.get(endpoint, params=params)

    assert response.status_code == 500
    assert response.json()["status"] == 500
    assert "data" not in response.json()


ASYNC_EVENT_CASES = [
    (
        "/events/start_upcoming_dividends_async",
        "/events/poll_upcoming_dividends_async",
        {"country": "AU", "index": "ASX200"},
        {"country": "Australia", "index": "asx200"},
        "app.routers.events_div.services_events_div.get_asx_upcoming_dividends_events",
        _dividend_event("ASX:ROUTEAU"),
    ),
    (
        "/events/start_upcoming_earnings_async",
        "/events/poll_upcoming_earnings_async",
        {"country": "US", "index": "SP500"},
        {"country": "U.S.A.", "index": "sp500"},
        "app.routers.events_earnings.services_events_earnings.get_us_upcoming_earnings_events",
        _earnings_event("NASDAQ:ROUTEUS"),
    ),
    (
        "/events/start_new_listings_async",
        "/events/poll_new_listings_async",
        {"country": "AU"},
        {"country": "Australia"},
        "app.routers.events_listings.services_asx_listings.ai_get_asx_new_listings",
        _listing_event("ASX:IPO", "2026-12-01"),
    ),
]


@pytest.mark.parametrize(
    ("start_endpoint", "poll_endpoint", "start_params", "duplicate_params", "target", "event"),
    ASYNC_EVENT_CASES,
)
def test_async_event_lifecycle_returns_running_then_completed_business_data(
    deferred_task_store,
    start_endpoint,
    poll_endpoint,
    start_params,
    duplicate_params,
    target,
    event,
):
    async def service(*args, **kwargs):
        return [event]

    with mock.patch(target, new=service):
        started = client.get(start_endpoint, params=start_params)
        task_id = started.json()["extra"]["task_id"]
        running = client.get(poll_endpoint, params={"task_id": task_id})
        duplicate_running = client.get(start_endpoint, params=duplicate_params)

        deferred_task_store.release()

        completed = client.get(poll_endpoint, params={"task_id": f"  {task_id}  "})
        duplicate_completed = client.get(start_endpoint, params=duplicate_params)

    assert started.status_code == 202
    assert running.status_code == 202
    assert duplicate_running.json()["extra"] == {"task_id": task_id, "state": "RUNNING"}
    assert completed.status_code == 200
    assert completed.json()["extra"] == {"task_id": task_id, "state": "COMPLETED"}
    assert completed.json()["data"][0]["symbol"] == event.symbol
    assert duplicate_completed.json() == completed.json()


@pytest.mark.parametrize(
    ("start_endpoint", "poll_endpoint", "start_params", "duplicate_params", "target", "event"),
    ASYNC_EVENT_CASES,
)
def test_async_event_background_failures_are_pollable_and_reused(
    deferred_task_store,
    start_endpoint,
    poll_endpoint,
    start_params,
    duplicate_params,
    target,
    event,
):
    del event

    async def fail(*args, **kwargs):
        raise RuntimeError("source unavailable")

    with mock.patch(target, new=fail):
        started = client.get(start_endpoint, params=start_params)
        task_id = started.json()["extra"]["task_id"]
        deferred_task_store.release()
        failed = client.get(poll_endpoint, params={"task_id": task_id})
        duplicate = client.get(start_endpoint, params=duplicate_params)

    assert started.status_code == 202
    assert failed.status_code == 500
    assert failed.json()["extra"] == {"task_id": task_id, "state": "FAILED"}
    assert "data" not in failed.json()
    assert duplicate.json() == failed.json()


@pytest.mark.parametrize(
    ("start_endpoint", "poll_endpoint", "params"),
    [
        (
            "/events/start_upcoming_dividends_async",
            "/events/poll_upcoming_dividends_async",
            {},
        ),
        (
            "/events/start_upcoming_earnings_async",
            "/events/poll_upcoming_earnings_async",
            {"country": "JP"},
        ),
    ],
)
def test_async_unsupported_event_country_completes_with_application_501(
    deferred_task_store,
    start_endpoint,
    poll_endpoint,
    params,
):
    started = client.get(start_endpoint, params=params)
    task_id = started.json()["extra"]["task_id"]
    deferred_task_store.release()

    completed = client.get(poll_endpoint, params={"task_id": task_id})
    duplicate = client.get(start_endpoint, params=params)

    assert started.status_code == 202
    assert completed.status_code == 200
    assert completed.json()["status"] == 501
    assert completed.json()["extra"] == {"task_id": task_id, "state": "COMPLETED"}
    assert "data" not in completed.json()
    assert duplicate.json() == completed.json()


@pytest.mark.parametrize("country", [None, "", "JP", "VN"])
def test_async_new_listings_requires_a_supported_country(country):
    params = {} if country is None else {"country": country}

    response = client.get("/events/start_new_listings_async", params=params)

    assert response.status_code == 422


def test_async_australian_and_us_listing_tasks_remain_distinct(deferred_task_store):
    async def au():
        return [_listing_event("ASX:IPO", "2026-12-01")]

    async def us():
        return [_listing_event("NASDAQ:IPO", "2026-12-02")]

    with (
        mock.patch(
            "app.routers.events_listings.services_asx_listings.ai_get_asx_new_listings",
            new=au,
        ),
        mock.patch(
            "app.routers.events_listings.services_us_listings.ai_get_us_new_listings",
            new=us,
        ),
    ):
        au_started = client.get(
            "/events/start_new_listings_async",
            params={"country": "AU"},
        )
        us_started = client.get(
            "/events/start_new_listings_async",
            params={"country": "US"},
        )
        deferred_task_store.release()
        au_completed = client.get(
            "/events/poll_new_listings_async",
            params={"task_id": au_started.json()["extra"]["task_id"]},
        )
        us_completed = client.get(
            "/events/poll_new_listings_async",
            params={"task_id": us_started.json()["extra"]["task_id"]},
        )

    assert au_started.json()["extra"]["task_id"] != us_started.json()["extra"]["task_id"]
    assert au_completed.json()["data"][0]["symbol"] == "ASX:IPO"
    assert us_completed.json()["data"][0]["symbol"] == "NASDAQ:IPO"


@pytest.mark.parametrize(
    "poll_endpoint",
    [
        "/events/poll_upcoming_dividends_async",
        "/events/poll_upcoming_earnings_async",
        "/events/poll_new_listings_async",
    ],
)
def test_async_event_poll_requires_task_id(poll_endpoint):
    response = client.get(poll_endpoint)

    assert response.status_code == 422
