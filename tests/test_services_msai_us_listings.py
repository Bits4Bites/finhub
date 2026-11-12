import asyncio
import copy
import datetime
import html
import json
import zoneinfo
from unittest import mock

import pandas as pd
import pytest

from app import config
from app.models import events_listings as models_events_listings
from app.services import ai_helper, msai_us_listings
from app.utils import ai_reference

_TODAY = datetime.date(2026, 11, 12)
_OVERVIEW_URL = "https://stockanalysis.com/stocks/example/"
_FILING_URL = "https://www.sec.gov/Archives/edgar/data/10001/00001000126000001/example_s1.htm"


@pytest.fixture(autouse=True)
def isolated_cache():
    entries = {}

    async def get(key):
        return copy.deepcopy(entries.get(key))

    async def set_value(key, value, *, ttl):
        assert ttl >= 3600
        entries[key] = copy.deepcopy(value)
        return True

    with (
        mock.patch.object(msai_us_listings.cache, "get", side_effect=get),
        mock.patch.object(msai_us_listings.cache, "set", side_effect=set_value),
        mock.patch.object(msai_us_listings, "_current_ny_date", return_value=_TODAY),
    ):
        yield entries


@pytest.fixture(autouse=True)
def ai_calls():
    with mock.patch.object(
        ai_helper,
        "ai_exec_task",
        new_callable=mock.AsyncMock,
        side_effect=AssertionError("Screening must not invoke AI"),
    ) as executor:
        yield executor


def _calendar_html(tables: list[pd.DataFrame]) -> str:
    parts = []
    for frame in tables:
        headers = "".join(f"<th>{html.escape(str(name))}</th>" for name in frame.columns)
        rows = []
        for row in frame.to_dict(orient="records"):
            cells = "".join(
                f"<td>{html.escape('-' if value is None or pd.isna(value) else str(value))}</td>"
                for value in row.values()
            )
            rows.append(f"<tr>{cells}</tr>")
        parts.append(f'<table id="main-table"><thead><tr>{headers}</tr></thead><tbody>{"".join(rows)}</tbody></table>')
    return "".join(parts)


def _listing_row(symbol: str = "EXAMPLE", **overrides) -> dict[str, object]:
    row: dict[str, object] = {
        "IPO Date": "Nov 12, 2026",
        "Symbol": symbol,
        "Company Name": "Example Inc.",
        "Exchange": "NASDAQ",
        "Price Range": "$11.00 - $13.00",
        "Shares Offered": "10,000,000",
        "Deal Size": "200.00M",
        "Market Cap": "1.29B",
        "Revenue": "49.68M",
    }
    row.update(overrides)
    return row


def test_extracts_prices_and_deal_sizes_from_all_three_tables():
    tables = [
        pd.DataFrame([_listing_row(" range ", **{"Exchange": "Nasdaq Global Select", "Company Name": " Range Inc. "})]),
        pd.DataFrame(
            [
                _listing_row(
                    "FIXED",
                    **{
                        "IPO Date": "Jul 15, 2027",
                        "Exchange": "NYSE",
                        "Price Range": "$12.50",
                        "Deal Size": "$1.25B",
                    },
                )
            ]
        ),
        pd.DataFrame(
            [
                _listing_row("SMALL", **{"Price Range": 1.25, "Deal Size": "1.001K"}),
                _listing_row("RANGE", **{"Price Range": "$100.00"}),
            ]
        ),
    ]

    with mock.patch.object(
        msai_us_listings.services_crawler,
        "fetch_webpage_content_fallback_to_playwright",
        new_callable=mock.AsyncMock,
        return_value=_calendar_html(tables),
    ) as mock_fetch:
        events = asyncio.run(msai_us_listings._get_us_new_listings())

    assert [event.symbol for event in events] == ["NASDAQ:RANGE", "NYSE:FIXED", "NASDAQ:SMALL"]
    ranged, fixed, small = events
    assert ranged.exchange == "NASDAQ"
    assert ranged.company_name == "Range Inc."
    assert ranged.issue_price == 11
    assert ranged.issue_price_upper == 13
    assert ranged.capital_to_raise == 200_000_000
    assert fixed.issue_price == 12.5
    assert fixed.issue_price_upper is None
    assert fixed.capital_to_raise == 1_250_000_000
    assert small.issue_price == 1.25
    assert small.issue_price_upper is None
    assert small.capital_to_raise == 1001
    ny_tz = zoneinfo.ZoneInfo("America/New_York")
    assert ranged.timestamp_str == "2026-11-12"
    assert ranged.timestamp == int(datetime.datetime(2026, 11, 12, tzinfo=ny_tz).timestamp())
    assert fixed.timestamp_str == "2027-07-15"
    assert fixed.timestamp == int(datetime.datetime(2027, 7, 15, tzinfo=ny_tz).timestamp())
    for event in events:
        assert event.currency == "USD"
        assert event.event_category == "listing"
        assert event.source_name == "Stock Analysis"
        assert event.link == "https://stockanalysis.com/ipos/calendar/"
    mock_fetch.assert_awaited_once_with("https://stockanalysis.com/ipos/calendar/", cache_ttl=3600)
    assert ranged._calendar_metrics == {
        "Shares Offered": "10,000,000",
        "Market Cap": "1.29B",
        "Revenue": "49.68M",
    }


@pytest.mark.parametrize("unavailable", [None, float("nan"), pd.NA, "-", "N/A", "TBD"])
def test_retains_listings_with_unavailable_offer_values(unavailable):
    tables = [
        pd.DataFrame(),
        pd.DataFrame([_listing_row(**{"Price Range": unavailable, "Deal Size": unavailable})]),
        pd.DataFrame(),
    ]
    with mock.patch.object(
        msai_us_listings.services_crawler,
        "fetch_webpage_content_fallback_to_playwright",
        new_callable=mock.AsyncMock,
        return_value=_calendar_html(tables),
    ):
        events = asyncio.run(msai_us_listings._get_us_new_listings())

    assert len(events) == 1
    assert events[0].issue_price is None
    assert events[0].issue_price_upper is None
    assert events[0].capital_to_raise is None


def test_invalid_rows_do_not_abort_other_listings():
    tables = [
        pd.DataFrame(
            [
                _listing_row("NODATE", **{"IPO Date": "TBD"}),
                _listing_row("ZERO", **{"Price Range": "$0"}),
                _listing_row("NEGATIVE", **{"Price Range": "-$1"}),
                _listing_row("REVERSED", **{"Price Range": "$13 - $11"}),
                _listing_row("BADPRICE", **{"Price Range": "$11 - TBD"}),
                _listing_row("NONFINITE", **{"Price Range": "Infinity"}),
                _listing_row("ZEROCAP", **{"Deal Size": "0"}),
                _listing_row("FRACTION", **{"Deal Size": "1.5"}),
                _listing_row(**{"Symbol": None}),
                _listing_row("NOEXCHANGE", **{"Exchange": None}),
            ]
        ),
        pd.DataFrame([_listing_row("VALID")]),
        pd.DataFrame(),
    ]
    with mock.patch.object(
        msai_us_listings.services_crawler,
        "fetch_webpage_content_fallback_to_playwright",
        new_callable=mock.AsyncMock,
        return_value=_calendar_html(tables),
    ):
        events = asyncio.run(msai_us_listings._get_us_new_listings())

    assert [event.symbol for event in events] == ["NASDAQ:VALID"]


def test_returns_no_listings_when_calendar_tables_are_empty():
    with mock.patch.object(
        msai_us_listings.services_crawler,
        "fetch_webpage_content_fallback_to_playwright",
        new_callable=mock.AsyncMock,
        return_value=_calendar_html([pd.DataFrame(), pd.DataFrame(), pd.DataFrame()]),
    ):
        events = asyncio.run(msai_us_listings._get_us_new_listings())

    assert events == []


def _event(symbol: str = "NASDAQ:EXAMPLE", **overrides) -> models_events_listings.ListingEvent:
    data = {
        "symbol": symbol,
        "exchange": symbol.split(":")[0],
        "company_name": "Example Inc.",
        "timestamp_str": "2026-11-12",
        "issue_price": 11,
        "issue_price_upper": 13,
        "currency": "USD",
        "capital_to_raise": 200_000_000,
    }
    data.update(overrides)
    return models_events_listings.ListingEvent(**data)


def _overview_html(**overrides) -> str:
    fields = {
        "Ticker Symbol": "EXAMPLE",
        "Stock Exchange": "Nasdaq",
        "IPO Date": "Nov 12, 2026",
        "IPO Price Range": "$11 - $13",
        "Industry": "Biotechnology",
        "Sector": "Healthcare",
        "Revenue (ttm)": "n/a",
        "Net Income": "-50M",
        "Market Cap": "1B",
        "Shares Out": "100M",
    }
    description = overrides.pop(
        "description", "Example develops clinical-stage treatments and has not yet commercialized its products."
    )
    status = overrides.pop("status", "Example will go public soon. The estimated IPO date is November 12, 2026.")
    filing = overrides.pop("filing", _FILING_URL)
    company = overrides.pop("company", "Example Inc.")
    fields.update(overrides)
    field_html = "".join(
        f"<div><span>{html.escape(name)}</span><span>{html.escape(value)}</span></div>"
        for name, value in fields.items()
        if value is not None
    )
    return (
        f"<main><h1>{html.escape(company)} (EXAMPLE)</h1><p>{status}</p>{field_html}"
        f"<h2>About EXAMPLE</h2><p>{description}</p>"
        f'<a href="{filing}">Example Inc. IPO Registration Document (S-1)</a>'
        '<a href="https://www.sec.gov/cgi-bin/browse-edgar?CIK=0000010001">SEC filings</a></main>'
    )


def _financials_html() -> str:
    return """
    <main>
      <div>Example Inc. (EXAMPLE)</div>
      <p>Financials in millions USD. Fiscal year is January - December.</p>
      <table>
        <thead>
          <tr><th>Fiscal Year</th><th>TTM</th><th>FY 2025</th></tr>
          <tr class="date-row"><th>Period Ending</th>
            <th title="Trailing twelve months ending Jun 30, 2026">Jun '26</th>
            <th><span>Dec '25</span><span>Dec 31, 2025</span></th>
          </tr>
        </thead>
        <tbody>
          <tr><td>Revenue</td><td>0</td><td>0</td></tr>
          <tr><td><span>Net Income</span><div aria-hidden="true">Net Income Growth</div></td>
            <td>-50</td><td>-30</td></tr>
          <tr><td>Cash &amp; Investments</td><td>25</td><td>30</td></tr>
          <tr><td>Operating Cash Flow</td><td>-45</td><td>-28</td></tr>
        </tbody>
      </table>
    </main>
    """


def _dossier(event: models_events_listings.ListingEvent, **overrides) -> msai_us_listings._ListingDossier:
    data = {
        "symbol": event.symbol,
        "overview_url": f"https://stockanalysis.com/stocks/{event.symbol.split(':')[1].lower()}/",
        "business_description": "Clinical-stage drug development.",
        "industry": "Biotechnology",
        "metrics": {"Market Cap": "1B", "Net Income": "-50M"},
        "financial_metrics": ["Net Income", "Operating Cash Flow"],
        "financial_periods": ["FY 2025", "TTM"],
        "filing_url": _FILING_URL,
        "filing_text": "The issuer offers common stock to fund clinical development.",
        "cik": "10001",
        "offering_type": "OperatingCompany",
        "is_active": True,
        "sources": {_OVERVIEW_URL: "Issuer and offer information."},
    }
    data.update(overrides)
    return msai_us_listings._ListingDossier(**data)


def _source_data(source_id: str = _OVERVIEW_URL) -> dict:
    return {
        "id": source_id,
        "title": "Example IPO",
        "publisher": "Stock Analysis",
        "source_type": "MarketData",
        "published_at": None,
        "accessed_at": "2020-01-01",
        "url": _OVERVIEW_URL,
    }


def _research_data(symbol: str = "NASDAQ:EXAMPLE", source_id: str = _OVERVIEW_URL) -> dict:
    return {
        "symbol": symbol,
        "as_of": "2026-11-12T00:00:00Z",
        **{
            name: {
                "facts": [
                    {"text": "The issuer is developing clinical-stage treatments.", "reference_ids": [source_id]}
                ],
                "reference_ids": [source_id],
                "data_gaps": [],
            }
            for name in msai_us_listings._RESEARCH_SECTION_NAMES
        },
        "references": [_source_data(source_id)],
    }


def _analysis_data(symbol: str = "NASDAQ:EXAMPLE") -> dict:
    source_id = ai_reference.generate_source_id(_OVERVIEW_URL)
    section = {
        "summary": "A provisional view of the offer.",
        "data_quality": "Medium",
        "facts": [{"text": "The issuer is developing clinical-stage treatments.", "reference_ids": [source_id]}],
        "reference_ids": [source_id],
        "assumptions": ["The offering proceeds."],
        "data_gaps": [],
    }
    data = {
        "symbol": symbol,
        "as_of": "2020-01-01T00:00:00Z",
        "listing_status": "Upcoming",
        "overall_data_quality": "Medium",
        "overall_stance": "Neutral",
        "overall_confidence": 45,
        "executive_summary": copy.deepcopy(section),
        "offer": {
            **copy.deepcopy(section),
            "issue_price_assessment": "The range is indicative.",
            "capital_raise_assessment": "Gross proceeds are not net funding.",
            "underwriting_assessment": "Commitment terms are unknown.",
            "use_of_funds": ["Clinical development"],
            "dilution_and_escrow": None,
        },
        "business": {
            **copy.deepcopy(section),
            "business_model": "Developing therapeutics.",
            "revenue_sources": [],
            "competitive_position": "Subject to clinical uncertainty.",
            "sector_context": "Milestone-driven.",
        },
        "financials": {
            **copy.deepcopy(section),
            "historical_performance": "Pre-revenue.",
            "profitability_and_cash_flow": "Loss-making.",
            "balance_sheet_and_funding": "Requires development funding.",
            "forecast_quality": "No commercial forecast established.",
        },
        "valuation": {
            **copy.deepcopy(section),
            "valuation_view": "Sensitive to clinical outcomes.",
            "implied_market_cap": None,
            "peer_comparison": "No comparable multiples verified.",
            "sensitivity": "Depends on milestones and funding.",
        },
        "governance": {
            **copy.deepcopy(section),
            "board_and_management": "Evidence limited.",
            "ownership_and_escrow": "Lock-ups not verified.",
            "governance_concerns": [],
        },
        "risks_and_catalysts": {**copy.deepcopy(section), "risks": [], "catalysts": []},
        "outlook": {
            name: {
                "assessment_type": "Forecast",
                "period_end": None,
                "direction": "Flat",
                "expected_price_min": 10,
                "expected_price_max": 15,
                "expected_return_min_pct": None,
                "expected_return_max_pct": None,
                "confidence": 40,
                "rationale": "A conditional trading scenario.",
                "key_drivers": ["Funding"],
                "risk_factors": ["Clinical uncertainty"],
                "assumptions": ["The offering proceeds."],
                "data_gaps": [],
                "reference_ids": [source_id],
            }
            for name in msai_us_listings._OUTLOOK_PERIOD_NAMES
        },
    }
    return data


def test_crawling_retains_pre_revenue_ipo_with_blocked_sec_document(ai_calls):
    async def fetch(url, **kwargs):
        if url == _FILING_URL:
            return None
        return _financials_html() if url.endswith("/financials/") else _overview_html()

    with (
        mock.patch.object(
            msai_us_listings.services_crawler, "fetch_webpage_content_fallback_to_playwright", side_effect=fetch
        ) as pages,
        mock.patch.object(
            msai_us_listings.services_crawler, "fetch_webpage_content", new_callable=mock.AsyncMock, return_value=None
        ) as direct_http,
    ):
        event = _event()
        dossier = asyncio.run(msai_us_listings._crawl_us_listing(event, today=_TODAY))

    assert msai_us_listings._eligible_for_analysis(dossier)
    assert dossier.industry == "Biotechnology"
    assert dossier.filing_url == _FILING_URL
    assert dossier.filing_text == ""
    assert any(_FILING_URL in gap for gap in dossier.data_gaps)
    assert dossier.financial_periods == ["FY 2025", "TTM"]
    assert "Operating Cash Flow" in dossier.financial_metrics
    financial_evidence = dossier.sources[f"{_OVERVIEW_URL}financials/"]
    assert "millions USD" in financial_evidence
    assert '"0"' in financial_evidence and '"-50"' in financial_evidence
    table = json.loads(financial_evidence.split("\n", 1)[1])[0]
    assert table["columns"] == ["Fiscal Year", "TTM", "FY 2025"]
    assert table["period_ending"] == ["Trailing twelve months ending Jun 30, 2026", "Dec 31, 2025"]
    assert event.industry == "Biotechnology"
    assert pages.await_count == 4
    pages.assert_any_await(_FILING_URL, cache_ttl=3600)
    direct_http.assert_not_awaited()
    ai_calls.assert_not_awaited()


def test_sec_filing_uses_browser_fallback_when_http_is_blocked(ai_calls):
    async def fetch(url, **kwargs):
        if url == _FILING_URL:
            return None
        return _financials_html() if url.endswith("/financials/") else _overview_html()

    filing_text = "Registration statement with audited financials and offer terms."
    with (
        mock.patch.object(msai_us_listings.services_crawler, "fetch_webpage_content", side_effect=fetch),
        mock.patch.object(
            msai_us_listings.services_crawler,
            "fetch_webpage_content_playwright",
            new_callable=mock.AsyncMock,
            return_value=f"<main>{filing_text}</main>",
        ) as browser,
    ):
        dossier = asyncio.run(msai_us_listings._crawl_us_listing(_event(), today=_TODAY))

    browser.assert_awaited_once_with(_FILING_URL, retries=2, cache_ttl=3600)
    assert dossier.filing_text == filing_text
    assert dossier.sources[_FILING_URL] == filing_text
    assert not any(_FILING_URL in gap for gap in dossier.data_gaps)
    ai_calls.assert_not_awaited()


def test_profile_uses_latest_amendment_instead_of_initial_news_link(ai_calls):
    amendment_url = _FILING_URL.replace("example_s1", "example_s1a")
    profile = _overview_html().replace(
        "</main>",
        "<h2>Latest SEC Filings</h2><table><tbody><tr>"
        f'<td>Nov 11, 2026</td><td>S-1/A</td><td><a href="{amendment_url}">Amended registration</a></td>'
        "</tr></tbody></table></main>",
    )

    async def fetch(url, **kwargs):
        if url == amendment_url:
            return None
        if url.endswith("/company/"):
            return profile
        return _financials_html() if url.endswith("/financials/") else _overview_html()

    with (
        mock.patch.object(
            msai_us_listings.services_crawler, "fetch_webpage_content_fallback_to_playwright", side_effect=fetch
        ) as pages,
        mock.patch.object(
            msai_us_listings.services_crawler, "fetch_webpage_content", new_callable=mock.AsyncMock, return_value=None
        ) as direct_http,
    ):
        dossier = asyncio.run(msai_us_listings._crawl_us_listing(_event(), today=_TODAY))

    assert dossier.filing_url == amendment_url
    assert dossier.filing_form == "S-1/A"
    assert dossier.filing_date == "Nov 11, 2026"
    assert msai_us_listings._eligible_for_analysis(dossier)
    pages.assert_any_await(amendment_url, cache_ttl=3600)
    direct_http.assert_not_awaited()
    ai_calls.assert_not_awaited()


@pytest.mark.parametrize(
    "overrides",
    [
        {"Industry": "Shell Companies", "description": "A newly organized blank check company."},
        {"Security Type": "Units"},
        {"status": "The IPO was withdrawn."},
        {"status": "The company is undertaking a direct listing."},
        {"Ticker Symbol": "OTHER"},
        {"company": "Unrelated Business Inc."},
        {"Stock Exchange": "NYSE"},
        {"IPO Date": "Nov 13, 2026"},
        {"IPO Price Range": "$20 - $25"},
        {"filing": _FILING_URL.replace("/10001/", "/99999/")},
    ],
)
def test_unsupported_inactive_or_conflicting_listings_do_not_reach_ai(overrides, ai_calls):
    async def fetch(url, **kwargs):
        return _overview_html(**overrides) if url == _OVERVIEW_URL else _financials_html()

    event = _event()
    with (
        mock.patch.object(
            msai_us_listings.services_crawler, "fetch_webpage_content_fallback_to_playwright", side_effect=fetch
        ),
        mock.patch.object(
            msai_us_listings.services_crawler, "fetch_webpage_content", new_callable=mock.AsyncMock, return_value=None
        ),
    ):
        events = asyncio.run(msai_us_listings._analyze_us_listings([event]))

    assert events == [event]
    assert event.analysis_status == "Skipped"
    assert event.analysis is None and event.analysis_error is None
    ai_calls.assert_not_awaited()


def test_missing_classification_gets_a_bounded_profile_crawl(ai_calls):
    async def fetch(url, **kwargs):
        if url == _FILING_URL:
            return None
        if url.endswith("/financials/"):
            return _financials_html()
        if url.endswith("/company/"):
            return _overview_html(description="Example develops treatments.", Industry="Biotechnology")
        return _overview_html(description="", Industry=None)

    with (
        mock.patch.object(
            msai_us_listings.services_crawler, "fetch_webpage_content_fallback_to_playwright", side_effect=fetch
        ) as pages,
        mock.patch.object(
            msai_us_listings.services_crawler, "fetch_webpage_content", new_callable=mock.AsyncMock, return_value=None
        ),
    ):
        dossier = asyncio.run(msai_us_listings._crawl_us_listing(_event(), today=_TODAY))

    assert msai_us_listings._eligible_for_analysis(dossier)
    assert dossier.business_description == "Example develops treatments."
    assert pages.await_count == 4
    assert dossier.page_count == 4
    ai_calls.assert_not_awaited()


def test_far_future_material_ipo_ranks_ahead_of_equally_ready_nearby_ipo(ai_calls):
    nearby = _event("NASDAQ:NEAR", capital_to_raise=20_000_000)
    distant = _event("NASDAQ:FAR", timestamp_str="2028-05-01", capital_to_raise=500_000_000)
    entries = [(nearby, _dossier(nearby)), (distant, _dossier(distant))]

    ranked = sorted(entries, key=lambda pair: msai_us_listings._candidate_sort_key(*pair, today=_TODAY))

    assert [event.symbol for event, _ in ranked] == ["NASDAQ:FAR", "NASDAQ:NEAR"]
    ai_calls.assert_not_awaited()


def test_top_five_failures_count_and_screening_failure_does_not_abort_others(ai_calls):
    events = [_event(f"NASDAQ:IPO{index}", capital_to_raise=(index + 1) * 100_000_000) for index in range(7)]

    async def crawl(event, **kwargs):
        if event.symbol == "NASDAQ:IPO0":
            raise RuntimeError("One page failed")
        return _dossier(event)

    with (
        mock.patch.object(msai_us_listings, "_crawl_us_listing", side_effect=crawl),
        mock.patch.object(
            msai_us_listings, "_research_us_listing", new_callable=mock.AsyncMock, side_effect=RuntimeError("AI failed")
        ) as research,
    ):
        result = asyncio.run(msai_us_listings._analyze_us_listings(events))

    assert [event.symbol for event in result] == [event.symbol for event in events]
    assert [event.analysis_status for event in result] == ["Skipped", "Skipped", *["Failed"] * 5]
    assert [call.args[0].symbol for call in research.await_args_list] == [
        f"NASDAQ:IPO{index}" for index in range(6, 1, -1)
    ]
    ai_calls.assert_not_awaited()


@pytest.mark.parametrize("citations, expected_verification", [([], False), ([_OVERVIEW_URL], True)])
def test_research_and_assessment_are_the_only_ai_stages_with_canonical_sources(
    ai_calls, citations, expected_verification
):
    event = _event()
    dossier = _dossier(event)
    ai_calls.side_effect = [
        ai_helper.LLMResponse(completion=json.dumps(_research_data()), citation_urls=citations),
        ai_helper.LLMResponse(completion=json.dumps(_analysis_data())),
    ]
    with mock.patch.object(msai_us_listings, "_crawl_us_listing", new_callable=mock.AsyncMock, return_value=dossier):
        events = asyncio.run(msai_us_listings._analyze_us_listings([event]))

    analysis = events[0].analysis
    assert events[0].analysis_status == "Completed"
    assert [call.args[0] for call in ai_calls.await_args_list] == ["US_LISTTINGS_RESEARCH", "US_LISTTINGS_ANALYZE"]
    assert all(call.kwargs["country"] == "US" for call in ai_calls.await_args_list)
    assert len(analysis.references) == 1
    assert analysis.references[0].id == ai_reference.generate_source_id(_OVERVIEW_URL)
    assert analysis.references[0].is_verified is expected_verification
    assert analysis.offer.facts[0].reference_ids == [analysis.references[0].id]
    assert analysis.outlook.first_month.reference_ids == [analysis.references[0].id]
    assert analysis.outlook.ipo_day.expected_return_min_pct == -9.09
    assert analysis.outlook.ipo_day.expected_return_max_pct == 36.36
    assert any("lower offer bound" in item for item in analysis.executive_summary.assumptions)
    assert any("aftermarket" in item for item in analysis.executive_summary.data_gaps)
    assert analysis.as_of.year != 2020


def test_unpriced_ipo_keeps_qualitative_analysis_without_invented_price_anchor(ai_calls):
    event = _event(issue_price=None, issue_price_upper=None)
    ai_calls.side_effect = [
        ai_helper.LLMResponse(completion=json.dumps(_research_data())),
        ai_helper.LLMResponse(completion=json.dumps(_analysis_data())),
    ]
    with mock.patch.object(
        msai_us_listings, "_crawl_us_listing", new_callable=mock.AsyncMock, return_value=_dossier(event)
    ):
        result = asyncio.run(msai_us_listings._analyze_us_listings([event]))

    assert result[0].analysis_status == "Completed"
    outlook = result[0].analysis.outlook.first_month
    assert outlook.direction == "Flat"
    assert outlook.expected_price_min is None and outlook.expected_price_max is None
    assert outlook.expected_return_min_pct is None and outlook.expected_return_max_pct is None


@pytest.mark.parametrize("invalid_stage", ["research", "assessment"])
def test_unsupported_source_links_fail_before_downstream_use(invalid_stage, ai_calls):
    research = _research_data()
    analysis = _analysis_data()
    if invalid_stage == "research":
        research["offer"]["facts"][0]["reference_ids"] = ["unknown-source"]
    else:
        analysis["outlook"]["ipo_day"]["reference_ids"] = ["unknown-source"]
    ai_calls.side_effect = [
        ai_helper.LLMResponse(completion=json.dumps(research)),
        ai_helper.LLMResponse(completion=json.dumps(analysis)),
    ]
    event = _event()
    with mock.patch.object(
        msai_us_listings, "_crawl_us_listing", new_callable=mock.AsyncMock, return_value=_dossier(event)
    ):
        result = asyncio.run(msai_us_listings._analyze_us_listings([event]))

    assert result[0].analysis_status == "Failed"
    assert result[0].analysis is None
    assert ai_calls.await_count == (1 if invalid_stage == "research" else 2)


def test_cached_analysis_avoids_ai_and_changed_filing_evidence_invalidates_it(ai_calls):
    event = _event()
    dossier = _dossier(event)
    ai_calls.side_effect = [
        ai_helper.LLMResponse(completion=json.dumps(_research_data())),
        ai_helper.LLMResponse(completion=json.dumps(_analysis_data())),
    ] * 2
    with mock.patch.object(
        msai_us_listings, "_crawl_us_listing", new_callable=mock.AsyncMock, side_effect=lambda *args, **kwargs: dossier
    ):
        first = asyncio.run(msai_us_listings._analyze_us_listings([event]))[0].analysis.model_dump()
        repeated = asyncio.run(msai_us_listings._analyze_us_listings([event]))[0].analysis.model_dump()
        assert repeated == first
        assert ai_calls.await_count == 2

        dossier.sources[_FILING_URL] = "An amended prospectus changes the issuer's funding needs."
        asyncio.run(msai_us_listings._analyze_us_listings([event]))

    assert ai_calls.await_count == 4
    assert event.analysis_status == "Completed"


def test_overridden_assessment_task_invalidates_analysis_but_reuses_research(ai_calls):
    event = _event()
    task = config.LLMTaskConfig(vendor="test", model="initial-model", tier="test")
    ai_calls.side_effect = [
        ai_helper.LLMResponse(completion=json.dumps(_research_data())),
        ai_helper.LLMResponse(completion=json.dumps(_analysis_data())),
        ai_helper.LLMResponse(completion=json.dumps(_analysis_data())),
    ]
    with (
        mock.patch.dict(config.settings_llm_task.tasks, {"US_LISTTINGS_ANALYZE": task}, clear=True),
        mock.patch.object(
            msai_us_listings, "_crawl_us_listing", new_callable=mock.AsyncMock, return_value=_dossier(event)
        ),
    ):
        asyncio.run(msai_us_listings._analyze_us_listings([event]))
        assert event.analysis_status == "Completed"
        task.model = "overridden-model"
        asyncio.run(msai_us_listings._analyze_us_listings([event]))

    assert event.analysis_status == "Completed"
    assert [call.args[0] for call in ai_calls.await_args_list] == [
        "US_LISTTINGS_RESEARCH",
        "US_LISTTINGS_ANALYZE",
        "US_LISTTINGS_ANALYZE",
    ]


def test_public_workflow_keeps_today_and_distant_events_in_date_order(ai_calls):
    past = _event("NASDAQ:PAST", timestamp_str="2026-11-11")
    today = _event("NASDAQ:TODAY")
    distant = _event("NASDAQ:FAR", timestamp_str="2028-05-01")
    with (
        mock.patch.object(
            msai_us_listings, "_get_us_new_listings", new_callable=mock.AsyncMock, return_value=[distant, past, today]
        ),
        mock.patch.object(
            msai_us_listings,
            "_crawl_us_listing",
            new_callable=mock.AsyncMock,
            return_value=_dossier(today, is_active=False),
        ),
    ):
        result = asyncio.run(msai_us_listings.ai_get_us_new_listings())

    assert [event.symbol for event in result] == ["NASDAQ:TODAY", "NASDAQ:FAR"]
    assert all(event.analysis_status == "Skipped" for event in result)
    assert result[0].timestamp_str == "2026-11-12 00:00:00-05:00"
    ai_calls.assert_not_awaited()
