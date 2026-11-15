import asyncio
import copy
import datetime
import html
import json
import zoneinfo
from unittest import mock

import pandas as pd
import pytest

from app.services import ai_helper
from app.services import msai_us_listings as service
from app.utils import ai_reference

_NY_TZ = zoneinfo.ZoneInfo("America/New_York")
_CALENDAR_URL = "https://stockanalysis.com/ipos/calendar/"
_FILING_URL = "https://www.sec.gov/Archives/edgar/data/10001/00001000126000001/example_s1.htm"


def _today() -> datetime.date:
    return datetime.datetime.now(_NY_TZ).date()


def _calendar_html(rows: list[dict[str, object]]) -> str:
    frame = pd.DataFrame(
        rows,
        columns=[
            "IPO Date",
            "Symbol",
            "Company Name",
            "Exchange",
            "Price Range",
            "Shares Offered",
            "Deal Size",
            "Market Cap",
            "Revenue",
        ],
    )
    headers = "".join(f"<th>{html.escape(str(name))}</th>" for name in frame.columns)
    body = []
    for row in frame.to_dict(orient="records"):
        cells = "".join(
            f"<td>{html.escape('-' if value is None or pd.isna(value) else str(value))}</td>" for value in row.values()
        )
        body.append(f"<tr>{cells}</tr>")
    return f'<table id="main-table"><thead><tr>{headers}</tr></thead><tbody>{"".join(body)}</tbody></table>'


def _listing_row(
    symbol: str = "EXAMPLE",
    *,
    listing_date: datetime.date | None = None,
    **overrides,
) -> dict[str, object]:
    listing_date = listing_date or _today()
    row: dict[str, object] = {
        "IPO Date": listing_date.strftime("%b %d, %Y"),
        "Symbol": symbol,
        "Company Name": f"{symbol.title()} Inc.",
        "Exchange": "NASDAQ",
        "Price Range": "$11.00 - $13.00",
        "Shares Offered": "10,000,000",
        "Deal Size": "200.00M",
        "Market Cap": "1.29B",
        "Revenue": "49.68M",
    }
    row.update(overrides)
    return row


def _overview_url(symbol: str = "EXAMPLE") -> str:
    return f"https://stockanalysis.com/stocks/{symbol.lower()}/"


def _overview_html(
    *,
    symbol: str = "EXAMPLE",
    listing_date: datetime.date | None = None,
) -> str:
    listing_date = listing_date or _today()
    company = f"{symbol.title()} Inc."
    fields = {
        "Ticker Symbol": symbol,
        "Stock Exchange": "Nasdaq",
        "IPO Date": listing_date.strftime("%b %d, %Y"),
        "IPO Price Range": "$11 - $13",
        "Industry": "Biotechnology",
        "Sector": "Healthcare",
        "Revenue (ttm)": "n/a",
        "Net Income": "-50M",
        "Market Cap": "1B",
        "Shares Out": "100M",
        "Security Type": "Common Stock",
        "CIK Code": "10001",
    }
    field_html = "".join(
        f"<div><span>{html.escape(name)}</span><span>{html.escape(value)}</span></div>"
        for name, value in fields.items()
    )
    return (
        f"<main><h1>{company} ({symbol})</h1>"
        f"<p>{company} will go public soon. The estimated IPO date is "
        f"{listing_date.strftime('%B %d, %Y')}.</p>"
        f"{field_html}"
        f"<h2>About {symbol}</h2>"
        "<p>The issuer develops clinical-stage treatments.</p>"
        f'<a href="{_FILING_URL}">Registration Document (S-1)</a>'
        '<a href="https://www.sec.gov/cgi-bin/browse-edgar?CIK=0000010001">'
        "SEC filings</a></main>"
    )


def _financials_html(symbol: str = "EXAMPLE") -> str:
    return f"""
    <main>
      <div>{symbol.title()} Inc. ({symbol})</div>
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
          <tr><td>Net Income</td><td>-50</td><td>-30</td></tr>
          <tr><td>Cash &amp; Investments</td><td>25</td><td>30</td></tr>
          <tr><td>Operating Cash Flow</td><td>-45</td><td>-28</td></tr>
        </tbody>
      </table>
    </main>
    """


def _research_response(symbol: str = "NASDAQ:EXAMPLE") -> ai_helper.LLMResponse:
    source_url = _overview_url(symbol.split(":", 1)[1])
    section = {
        "facts": [
            {
                "text": "The issuer develops clinical-stage treatments.",
                "reference_ids": [source_url],
            }
        ],
        "reference_ids": [source_url],
        "data_gaps": [],
    }
    payload = {
        "symbol": symbol,
        "as_of": datetime.datetime.now(datetime.UTC).isoformat(),
        "offer": copy.deepcopy(section),
        "business": copy.deepcopy(section),
        "financials": copy.deepcopy(section),
        "valuation": copy.deepcopy(section),
        "governance": copy.deepcopy(section),
        "market_context": copy.deepcopy(section),
        "risks_and_catalysts": copy.deepcopy(section),
        "references": [
            {
                "id": source_url,
                "title": "Example IPO",
                "publisher": "Stock Analysis",
                "source_type": "MarketData",
                "published_at": None,
                "accessed_at": datetime.datetime.now(datetime.UTC).isoformat(),
                "url": source_url,
            }
        ],
    }
    return ai_helper.LLMResponse(
        completion=json.dumps(payload),
        citation_urls=[source_url],
    )


def _analysis_section(source_id: str) -> dict[str, object]:
    return {
        "summary": "A provisional view of the offer.",
        "data_quality": "Medium",
        "facts": [
            {
                "text": "The issuer develops clinical-stage treatments.",
                "reference_ids": [source_id],
            }
        ],
        "reference_ids": [source_id],
        "assumptions": ["The offering proceeds."],
        "data_gaps": [],
    }


def _analysis_response(symbol: str = "NASDAQ:EXAMPLE") -> ai_helper.LLMResponse:
    source_id = ai_reference.generate_source_id(_overview_url(symbol.split(":", 1)[1]))
    section = _analysis_section(source_id)
    period = {
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
    payload = {
        "symbol": symbol,
        "as_of": datetime.datetime.now(datetime.UTC).isoformat(),
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
        "risks_and_catalysts": {
            **copy.deepcopy(section),
            "risks": [],
            "catalysts": [],
        },
        "outlook": {
            "ipo_day": copy.deepcopy(period),
            "first_week": copy.deepcopy(period),
            "first_two_weeks": copy.deepcopy(period),
            "first_month": copy.deepcopy(period),
        },
    }
    return ai_helper.LLMResponse(completion=json.dumps(payload))


@pytest.fixture(autouse=True)
def isolated_cache():
    entries: dict[str, object] = {}

    async def get(key):
        return copy.deepcopy(entries.get(key))

    async def set_value(key, value, *, ttl):
        assert ttl >= 60 * 60
        entries[key] = copy.deepcopy(value)
        return True

    with (
        mock.patch.object(service.cache, "get", side_effect=get),
        mock.patch.object(service.cache, "set", side_effect=set_value),
    ):
        yield entries


def test_public_workflow_returns_empty_list_for_empty_calendar():
    with (
        mock.patch.object(
            service.services_crawler_core,
            "fetch_webpage_content_fallback_to_playwright",
            new_callable=mock.AsyncMock,
            return_value=_calendar_html([]),
        ),
        mock.patch.object(
            service.ai_helper,
            "ai_exec_task",
            new_callable=mock.AsyncMock,
        ) as ai_exec,
    ):
        result = asyncio.run(service.ai_get_us_new_listings())

    assert result == []
    ai_exec.assert_not_awaited()


def test_public_workflow_reports_calendar_fetch_failure():
    with (
        mock.patch.object(
            service.services_crawler_core,
            "fetch_webpage_content_fallback_to_playwright",
            new_callable=mock.AsyncMock,
            return_value=None,
        ),
        pytest.raises(RuntimeError, match="Failed to fetch the IPO calendar"),
    ):
        asyncio.run(service.ai_get_us_new_listings())


def test_public_workflow_filters_orders_and_retains_unavailable_offer_values():
    today = _today()
    rows = [
        _listing_row("FUTURE", listing_date=today + datetime.timedelta(days=3)),
        _listing_row("PAST", listing_date=today - datetime.timedelta(days=1)),
        _listing_row(
            "TODAY",
            listing_date=today,
            **{"Price Range": None, "Deal Size": None},
        ),
    ]

    async def fetch(url, **_kwargs):
        return _calendar_html(rows) if url == _CALENDAR_URL else None

    with (
        mock.patch.object(
            service.services_crawler_core,
            "fetch_webpage_content_fallback_to_playwright",
            side_effect=fetch,
        ),
        mock.patch.object(
            service.ai_helper,
            "ai_exec_task",
            new_callable=mock.AsyncMock,
        ) as ai_exec,
    ):
        result = asyncio.run(service.ai_get_us_new_listings())

    assert [event.symbol for event in result] == [
        "NASDAQ:TODAY",
        "NASDAQ:FUTURE",
    ]
    assert result[0].issue_price is None
    assert result[0].issue_price_upper is None
    assert result[0].capital_to_raise is None
    assert all(event.analysis_status == "Skipped" for event in result)
    assert result[0].timestamp_str.startswith(today.isoformat())
    ai_exec.assert_not_awaited()


def test_company_crawl_failure_is_returned_as_skipped_event():
    rows = [_listing_row()]

    async def fetch(url, **_kwargs):
        if url == _CALENDAR_URL:
            return _calendar_html(rows)
        raise OSError("company page unavailable")

    with (
        mock.patch.object(
            service.services_crawler_core,
            "fetch_webpage_content_fallback_to_playwright",
            side_effect=fetch,
        ),
        mock.patch.object(
            service.ai_helper,
            "ai_exec_task",
            new_callable=mock.AsyncMock,
        ) as ai_exec,
    ):
        result = asyncio.run(service.ai_get_us_new_listings())

    assert len(result) == 1
    assert result[0].analysis_status == "Skipped"
    assert result[0].analysis is None
    assert result[0].analysis_error is None
    ai_exec.assert_not_awaited()


def test_completed_analysis_is_reused_from_cache(isolated_cache):
    rows = [_listing_row()]

    async def fetch(url, **_kwargs):
        if url == _CALENDAR_URL:
            return _calendar_html(rows)
        if url.endswith("/financials/"):
            return _financials_html()
        if url == _FILING_URL:
            return "<main>Registration statement and audited financials.</main>"
        return _overview_html()

    with (
        mock.patch.object(
            service.services_crawler_core,
            "fetch_webpage_content_fallback_to_playwright",
            side_effect=fetch,
        ),
        mock.patch.object(
            service.ai_helper,
            "ai_exec_task",
            new_callable=mock.AsyncMock,
            side_effect=[_research_response(), _analysis_response()],
        ) as ai_exec,
    ):
        first = asyncio.run(service.ai_get_us_new_listings())
        second = asyncio.run(service.ai_get_us_new_listings())

    assert first == second
    assert len(first) == 1
    assert first[0].analysis_status == "Completed"
    assert first[0].analysis is not None
    assert first[0].analysis.references[0].is_verified is True
    assert first[0].analysis.outlook.ipo_day.expected_return_min_pct == -9.09
    assert first[0].analysis.outlook.ipo_day.expected_return_max_pct == 36.36
    assert ai_exec.await_count == 2
    assert isolated_cache


def test_selected_analysis_cache_failure_is_returned_as_failed_event():
    rows = [_listing_row()]

    async def fetch(url, **_kwargs):
        if url == _CALENDAR_URL:
            return _calendar_html(rows)
        if url.endswith("/financials/"):
            return _financials_html()
        if url == _FILING_URL:
            return "<main>Registration statement and audited financials.</main>"
        return _overview_html()

    with (
        mock.patch.object(
            service.services_crawler_core,
            "fetch_webpage_content_fallback_to_playwright",
            side_effect=fetch,
        ),
        mock.patch.object(
            service.cache,
            "get",
            new_callable=mock.AsyncMock,
            side_effect=ConnectionError("cache unavailable"),
        ),
        mock.patch.object(
            service.ai_helper,
            "ai_exec_task",
            new_callable=mock.AsyncMock,
        ) as ai_exec,
    ):
        result = asyncio.run(service.ai_get_us_new_listings())

    assert len(result) == 1
    assert result[0].analysis_status == "Failed"
    assert result[0].analysis is None
    assert result[0].analysis_error == "AI listing analysis failed"
    ai_exec.assert_not_awaited()


def test_selected_ai_failure_is_returned_as_failed_event():
    rows = [_listing_row()]

    async def fetch(url, **_kwargs):
        if url == _CALENDAR_URL:
            return _calendar_html(rows)
        if url.endswith("/financials/"):
            return _financials_html()
        if url == _FILING_URL:
            return "<main>Registration statement and audited financials.</main>"
        return _overview_html()

    with (
        mock.patch.object(
            service.services_crawler_core,
            "fetch_webpage_content_fallback_to_playwright",
            side_effect=fetch,
        ),
        mock.patch.object(
            service.ai_helper,
            "ai_exec_task",
            new_callable=mock.AsyncMock,
            return_value=ai_helper.LLMResponse(
                is_error=True,
                error_msg="provider rejected the request",
            ),
        ),
    ):
        result = asyncio.run(service.ai_get_us_new_listings())

    assert len(result) == 1
    assert result[0].analysis_status == "Failed"
    assert result[0].analysis is None
    assert result[0].analysis_error == "AI listing analysis failed"
