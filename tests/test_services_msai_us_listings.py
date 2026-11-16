"""Documentation-driven black-box tests for US listing analysis."""

import asyncio
import copy
import datetime
import html
import json
import re
import zoneinfo
from unittest import mock

import pandas as pd
import pytest

from app.services import ai_helper
from app.services import msai_us_listings as service
from app.utils import ai_reference
from tests import ai_service_fixtures

_NY_TZ = zoneinfo.ZoneInfo("America/New_York")
_CALENDAR_URL = "https://stockanalysis.com/ipos/calendar/"


class CrawlerBoundary:
    def __init__(
        self,
        rows: list[dict[str, object]],
        *,
        low_readiness_symbols: set[str] | None = None,
        unsupported_symbols: set[str] | None = None,
        failing_symbols: set[str] | None = None,
    ) -> None:
        self.rows = rows
        self.low_readiness_symbols = low_readiness_symbols or set()
        self.unsupported_symbols = unsupported_symbols or set()
        self.failing_symbols = failing_symbols or set()
        self.listing_dates = {
            str(row["Symbol"]).upper(): datetime.datetime.strptime(
                str(row["IPO Date"]),
                "%b %d, %Y",
            ).date()
            for row in rows
        }

    async def __call__(self, url: str, **_kwargs) -> str | None:
        if url == _CALENDAR_URL:
            return _calendar_html(self.rows)

        filing_match = re.search(r"/([a-z0-9.-]+)_s1\.htm$", url, re.IGNORECASE)
        if filing_match:
            symbol = filing_match.group(1).upper()
            if symbol in self.low_readiness_symbols:
                return None
            return "<main>Registration statement and audited financials.</main>"

        symbol_match = re.search(r"/stocks/([a-z0-9.-]+)/", url, re.IGNORECASE)
        if symbol_match is None:
            return None
        symbol = symbol_match.group(1).upper()
        if symbol in self.failing_symbols:
            raise OSError("company page unavailable")
        if url.endswith("/financials/"):
            if symbol in self.low_readiness_symbols:
                return None
            return _financials_html(symbol)
        return _overview_html(
            symbol=symbol,
            listing_date=self.listing_dates[symbol],
            unsupported=symbol in self.unsupported_symbols,
        )


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


def _overview_url(symbol: str) -> str:
    return f"https://stockanalysis.com/stocks/{symbol.lower()}/"


def _filing_url(symbol: str) -> str:
    return f"https://www.sec.gov/Archives/edgar/data/10001/00001000126000001/{symbol.lower()}_s1.htm"


def _overview_html(
    *,
    symbol: str,
    listing_date: datetime.date,
    unsupported: bool = False,
) -> str:
    company = f"{symbol.title()} Inc."
    fields = {
        "Ticker Symbol": symbol,
        "Stock Exchange": "Nasdaq",
        "IPO Date": listing_date.strftime("%b %d, %Y"),
        "IPO Price Range": "$11 - $13",
        "Industry": "Shell Companies" if unsupported else "Biotechnology",
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
    description = (
        "A blank-check company seeking an acquisition."
        if unsupported
        else "The issuer develops clinical-stage treatments."
    )
    return (
        f"<main><h1>{company} ({symbol})</h1>"
        f"<p>{company} will go public soon. The estimated IPO date is "
        f"{listing_date.strftime('%B %d, %Y')}.</p>"
        f"{field_html}"
        f"<h2>About {symbol}</h2>"
        f"<p>{description}</p>"
        f'<a href="{_filing_url(symbol)}">Registration Document (S-1)</a>'
        '<a href="https://www.sec.gov/cgi-bin/browse-edgar?CIK=0000010001">'
        "SEC filings</a></main>"
    )


def _financials_html(symbol: str) -> str:
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


def _research_payload(symbol: str) -> dict[str, object]:
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
    return {
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


def _research_response(
    symbol: str,
    *,
    verified: bool = True,
) -> ai_helper.LLMResponse:
    source_url = _overview_url(symbol.split(":", 1)[1])
    return ai_helper.LLMResponse(
        completion=json.dumps(_research_payload(symbol)),
        citation_urls=[source_url] if verified else [],
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


def _analysis_payload(symbol: str) -> dict[str, object]:
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
    return {
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


def _analysis_response(symbol: str) -> ai_helper.LLMResponse:
    return ai_helper.LLMResponse(completion=json.dumps(_analysis_payload(symbol)))


def _ai_error_response() -> ai_helper.LLMResponse:
    return ai_helper.LLMResponse(
        is_error=True,
        completion="provider rejected the request",
        error_msg="provider rejected the request",
    )


def _run(
    *,
    crawler: CrawlerBoundary,
    ai: ai_service_fixtures.OpaqueAIQueue | None = None,
    cache=None,
):
    ai = ai or ai_service_fixtures.OpaqueAIQueue()
    cache = cache or ai_service_fixtures.ExpiringCache()
    with (
        mock.patch.object(
            service.services_crawler_core,
            "fetch_webpage_content_fallback_to_playwright",
            new=crawler,
        ),
        mock.patch.object(service.cache, "get", side_effect=cache.get),
        mock.patch.object(service.cache, "set", side_effect=cache.set),
        mock.patch.object(service.ai_helper, "ai_exec_task", new=ai),
    ):
        return asyncio.run(service.ai_get_us_new_listings())


def test_empty_calendar_returns_empty_list():
    assert _run(crawler=CrawlerBoundary([])) == []


def test_calendar_fetch_failure_raises_documented_runtime_error():
    with (
        mock.patch.object(
            service.services_crawler_core,
            "fetch_webpage_content_fallback_to_playwright",
            new_callable=mock.AsyncMock,
            return_value=None,
        ),
        pytest.raises(RuntimeError),
    ):
        asyncio.run(service.ai_get_us_new_listings())


def test_filters_orders_and_retains_unavailable_offer_values():
    today = _today()
    rows = [
        _listing_row("FUTURE", listing_date=today + datetime.timedelta(days=3)),
        _listing_row("PAST", listing_date=today - datetime.timedelta(days=1)),
        _listing_row(
            "TODAY",
            listing_date=today,
            **{"Price Range": None, "Deal Size": None},
        ),
        _listing_row("NANPRICE", listing_date=today, **{"Price Range": "$NaN - $13"}),
        _listing_row("NEGINFRAISE", listing_date=today, **{"Deal Size": "-Infinity"}),
    ]
    crawler = CrawlerBoundary(rows, failing_symbols={"FUTURE", "TODAY"})

    result = _run(crawler=crawler)

    assert [event.symbol for event in result] == ["NASDAQ:TODAY", "NASDAQ:FUTURE"]
    assert result[0].issue_price is None
    assert result[0].issue_price_upper is None
    assert result[0].capital_to_raise is None
    assert all(event.analysis_status == "Skipped" for event in result)
    assert result[0].timestamp_str.startswith(today.isoformat())


def test_readiness_ranking_and_symbol_tie_break_select_five_of_seven_eligible_events():
    today = _today()
    rows = [
        *[
            _listing_row(
                f"TIE{index}",
                listing_date=today,
                **{"Deal Size": "100.00M"},
            )
            for index in range(1, 7)
        ],
        _listing_row(
            "LOW",
            listing_date=today,
            **{"Deal Size": "999.00M"},
        ),
        _listing_row("SPAC", listing_date=today),
    ]
    crawler = CrawlerBoundary(
        rows,
        low_readiness_symbols={"LOW"},
        unsupported_symbols={"SPAC"},
    )
    ai = ai_service_fixtures.OpaqueAIQueue(
        [
            item
            for index in range(1, 6)
            for item in (
                _research_response(f"NASDAQ:TIE{index}"),
                _analysis_response(f"NASDAQ:TIE{index}"),
            )
        ]
    )

    events = _run(crawler=crawler, ai=ai)
    statuses = {event.symbol: event.analysis_status for event in events}

    assert len(events) == 8
    assert {statuses[f"NASDAQ:TIE{index}"] for index in range(1, 6)} == {"Completed"}
    assert statuses["NASDAQ:TIE6"] == "Skipped"
    assert statuses["NASDAQ:LOW"] == "Skipped"
    assert statuses["NASDAQ:SPAC"] == "Skipped"
    assert next(event for event in events if event.symbol == "NASDAQ:LOW").analysis is None
    assert next(event for event in events if event.symbol == "NASDAQ:SPAC").analysis is None


def test_offer_price_return_semantics_and_missing_anchor_behavior():
    priced_rows = [_listing_row("PRICED")]
    priced = _run(
        crawler=CrawlerBoundary(priced_rows),
        ai=ai_service_fixtures.OpaqueAIQueue(
            [
                _research_response("NASDAQ:PRICED"),
                _analysis_response("NASDAQ:PRICED"),
            ]
        ),
    )[0]
    assert priced.analysis is not None
    priced_period = priced.analysis.outlook.ipo_day
    assert priced_period.expected_return_min_pct == pytest.approx(
        round((priced_period.expected_price_min / priced.issue_price - 1) * 100, 2)
    )
    assert priced_period.expected_return_max_pct == pytest.approx(
        round((priced_period.expected_price_max / priced.issue_price - 1) * 100, 2)
    )

    unpriced_rows = [_listing_row("UNPRICED", **{"Price Range": None})]
    unpriced = _run(
        crawler=CrawlerBoundary(unpriced_rows),
        ai=ai_service_fixtures.OpaqueAIQueue(
            [
                _research_response("NASDAQ:UNPRICED"),
                _analysis_response("NASDAQ:UNPRICED"),
            ]
        ),
    )[0]
    assert unpriced.analysis is not None
    unpriced_period = unpriced.analysis.outlook.ipo_day
    assert unpriced_period.expected_price_min is None
    assert unpriced_period.expected_price_max is None
    assert unpriced_period.expected_return_min_pct is None
    assert unpriced_period.expected_return_max_pct is None


def test_unmatched_provider_citations_are_retained_as_unverified_warnings():
    rows = [_listing_row("UNVERIFIED")]
    event = _run(
        crawler=CrawlerBoundary(rows),
        ai=ai_service_fixtures.OpaqueAIQueue(
            [
                _research_response("NASDAQ:UNVERIFIED", verified=False),
                _analysis_response("NASDAQ:UNVERIFIED"),
            ]
        ),
    )[0]

    assert event.analysis_status == "Completed"
    assert event.analysis is not None
    assert event.analysis.references
    assert all(reference.is_verified is False for reference in event.analysis.references)
    assert event.analysis.executive_summary.data_gaps


def test_repeated_public_call_reuses_completed_analysis_when_ai_is_unavailable():
    rows = [_listing_row("CACHE")]
    crawler = CrawlerBoundary(rows)
    cache = ai_service_fixtures.ExpiringCache()
    ai = ai_service_fixtures.OpaqueAIQueue(
        [
            _research_response("NASDAQ:CACHE"),
            _analysis_response("NASDAQ:CACHE"),
        ]
    )

    first = _run(crawler=crawler, ai=ai, cache=cache)
    second = _run(crawler=crawler, ai=ai, cache=cache)

    assert second == first
    assert second[0].analysis_status == "Completed"
    assert second[0].analysis is not None


def test_documented_one_hour_cache_expiry_reenters_analysis():
    rows = [_listing_row("EXPIRY")]
    crawler = CrawlerBoundary(rows)
    clock = ai_service_fixtures.ManualClock()
    cache = ai_service_fixtures.ExpiringCache(clock)
    ai = ai_service_fixtures.OpaqueAIQueue(
        [
            _research_response("NASDAQ:EXPIRY"),
            _analysis_response("NASDAQ:EXPIRY"),
        ]
    )

    first = _run(crawler=crawler, ai=ai, cache=cache)
    clock.advance(60 * 60 - 1)
    assert _run(crawler=crawler, ai=ai, cache=cache) == first
    clock.advance(1)
    expired = _run(crawler=crawler, ai=ai, cache=cache)

    assert expired[0].analysis_status == "Failed"
    assert expired[0].analysis is None


def test_opaque_invalid_selected_analysis_cache_returns_failed_event():
    rows = [_listing_row("INVALID")]
    result = _run(
        crawler=CrawlerBoundary(rows),
        cache=ai_service_fixtures.InvalidCache(object()),
    )

    assert len(result) == 1
    assert result[0].analysis_status == "Failed"
    assert result[0].analysis is None
    assert result[0].analysis_error


def test_selected_ai_failure_is_retained_as_failed_event():
    rows = [_listing_row("FAILED")]
    result = _run(
        crawler=CrawlerBoundary(rows),
        ai=ai_service_fixtures.OpaqueAIQueue([_ai_error_response()]),
    )

    assert len(result) == 1
    assert result[0].analysis_status == "Failed"
    assert result[0].analysis is None
    assert result[0].analysis_error
