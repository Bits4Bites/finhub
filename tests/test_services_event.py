import asyncio
import datetime
import json
import math
import threading
import zoneinfo
from unittest.mock import AsyncMock, patch
from urllib.parse import urlparse

import pandas as pd
import pytest

from app.services import events_div, events_earnings
from app.services import market as services_market

DIVIDEND_COLUMNS = [
    "Ticker",
    "Company",
    "Ex-Div Date",
    "Payment Date",
    "Div Amount",
    "Div Yield",
    "Market Cap",
    "Exchange",
    "Currency",
]
EARNINGS_COLUMNS = [
    "Announcement Date",
    "Exchange",
    "Ticker",
    "Company",
    "Market Cap",
    "EPS",
    "EPS Forecast",
    "Revenue",
    "Revenue Forecast",
    "Currency",
]


class _FixedDateTime(datetime.datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 11, 16, 12, tzinfo=tz)


def _dividend_frame(rows):
    return pd.DataFrame(rows, columns=DIVIDEND_COLUMNS)


def _dividend_row(
    symbol,
    company,
    *,
    exchange="ASX",
    currency="AUD",
    ex_date="2026-11-20",
    payment_date="2026-12-15",
):
    return {
        "Ticker": symbol,
        "Company": company,
        "Ex-Div Date": ex_date,
        "Payment Date": payment_date,
        "Div Amount": 1.5,
        "Div Yield": 0.03,
        "Market Cap": 1_000_000_000,
        "Exchange": exchange,
        "Currency": currency,
    }


def _earnings_frame(rows):
    return pd.DataFrame(rows, columns=EARNINGS_COLUMNS)


def _earnings_row(
    symbol,
    company,
    *,
    exchange="ASX",
    currency="AUD",
    announcement_date="2026-11-20",
):
    return {
        "Announcement Date": announcement_date,
        "Exchange": exchange,
        "Ticker": symbol,
        "Company": company,
        "Market Cap": 1_000_000_000,
        "EPS": -1.25,
        "EPS Forecast": 0.0,
        "Revenue": 0,
        "Revenue Forecast": 1_001_000_000,
        "Currency": currency,
    }


def _store_with_index(index, *symbols):
    store = services_market.MarketIndexStore()
    store.load(
        index,
        json.dumps(
            {
                "data": [
                    {
                        "symbol": symbol,
                        "company": symbol,
                    }
                    for symbol in symbols
                ]
            }
        ),
    )
    return store


class TestEarningsEvents:
    @pytest.mark.parametrize(
        ("public_function", "crawler_target", "invalid_index"),
        [
            (
                events_earnings.get_asx_upcoming_earnings_events,
                "app.services.events_earnings.services_crawler_earnings.scrape_earnings_asx",
                "SP500",
            ),
            (
                events_earnings.get_us_upcoming_earnings_events,
                "app.services.events_earnings.services_crawler_earnings.scrape_earnings_us",
                "ASX200",
            ),
        ],
    )
    def test_invalid_index_returns_empty(self, public_function, crawler_target, invalid_index):
        with patch(crawler_target, new_callable=AsyncMock, return_value=pd.DataFrame()):
            result = asyncio.run(public_function(invalid_index))

        assert result == []

    def test_asx_events_return_normalized_public_models(self):
        raw_data = _earnings_frame([_earnings_row("CBA", "Commonwealth Bank")])

        with patch(
            "app.services.events_earnings.services_crawler_earnings.scrape_earnings_asx",
            new_callable=AsyncMock,
            return_value=raw_data,
        ):
            result = asyncio.run(events_earnings.get_asx_upcoming_earnings_events())

        assert len(result) == 1
        earnings = result[0]
        assert earnings.symbol == "ASX:CBA"
        assert earnings.exchange == "ASX"
        assert earnings.company_name == "Commonwealth Bank"
        assert earnings.timestamp_str == "2026-11-20 00:00:00+11:00"
        assert earnings.timestamp == int(
            datetime.datetime(2026, 11, 20, tzinfo=zoneinfo.ZoneInfo("Australia/Sydney")).timestamp()
        )
        assert earnings.event_category == "earnings"
        assert earnings.source_name
        assert earnings.status == "estimated"
        assert earnings.report_period == "N/A"
        assert urlparse(earnings.link).scheme in {"http", "https"}
        assert urlparse(earnings.link).netloc

    def test_asx_index_filter_is_case_insensitive(self):
        raw_data = _earnings_frame(
            [
                _earnings_row("WBC", "Westpac", announcement_date="2026-11-19"),
                _earnings_row("CBA", "Commonwealth Bank"),
            ]
        )
        store = _store_with_index("ASX20", "ASX:CBA")

        with (
            patch.object(services_market, "market_indices", store),
            patch(
                "app.services.events_earnings.services_crawler_earnings.scrape_earnings_asx",
                new_callable=AsyncMock,
                return_value=raw_data,
            ),
        ):
            result = asyncio.run(events_earnings.get_asx_upcoming_earnings_events("asx20"))

        assert [earnings.symbol for earnings in result] == ["ASX:CBA"]

    def test_us_events_keep_major_exchanges_in_source_order(self):
        raw_data = _earnings_frame(
            [
                _earnings_row("MSFT", "Microsoft", exchange="NYSE", currency="USD", announcement_date="2026-11-18"),
                _earnings_row("PINK1", "Pink Sheets Co", exchange="PINK", currency="USD"),
                _earnings_row("UNKNOWN", "Unknown Co", exchange="N/A", currency="USD"),
                _earnings_row("NOEXCHANGE", "No Exchange Co", exchange="", currency="USD"),
                _earnings_row("AAPL", "Apple Inc.", exchange="NASDAQ", currency="USD"),
            ]
        )

        with patch(
            "app.services.events_earnings.services_crawler_earnings.scrape_earnings_us",
            new_callable=AsyncMock,
            return_value=raw_data,
        ):
            result = asyncio.run(events_earnings.get_us_upcoming_earnings_events())

        assert [earnings.symbol for earnings in result] == ["NYSE:MSFT", "NASDAQ:AAPL"]
        assert [earnings.company_name for earnings in result] == ["Microsoft", "Apple Inc."]
        assert all(urlparse(earnings.link).scheme in {"http", "https"} for earnings in result)
        assert all(urlparse(earnings.link).netloc for earnings in result)
        assert len({earnings.link for earnings in result}) == len(result)
        assert all(earnings.timestamp_str.endswith("-05:00") for earnings in result)
        assert all(earnings.status == "estimated" for earnings in result)
        assert all(earnings.report_period == "N/A" for earnings in result)

    def test_us_events_without_a_supported_exchange_return_empty(self):
        raw_data = _earnings_frame(
            [
                _earnings_row("UNKNOWN", "Unknown Co", exchange=exchange, currency="USD")
                for exchange in ["N/A", "", "PINK"]
            ]
        )
        with patch(
            "app.services.events_earnings.services_crawler_earnings.scrape_earnings_us",
            new_callable=AsyncMock,
            return_value=raw_data,
        ):
            assert asyncio.run(events_earnings.get_us_upcoming_earnings_events()) == []

    @pytest.mark.parametrize(
        ("public_function", "crawler_target"),
        [
            (
                events_earnings.get_asx_upcoming_earnings_events,
                "app.services.events_earnings.services_crawler_earnings.scrape_earnings_asx",
            ),
            (
                events_earnings.get_us_upcoming_earnings_events,
                "app.services.events_earnings.services_crawler_earnings.scrape_earnings_us",
            ),
        ],
        ids=["asx", "us"],
    )
    def test_empty_crawler_frame_returns_no_events(self, public_function, crawler_target):
        with patch(crawler_target, new_callable=AsyncMock, return_value=_earnings_frame([])):
            assert asyncio.run(public_function()) == []

    @pytest.mark.parametrize(
        "public_function",
        [
            events_earnings.get_asx_upcoming_earnings_events,
            events_earnings.get_us_upcoming_earnings_events,
        ],
        ids=["asx", "us"],
    )
    def test_missing_crawled_ticker_is_rejected(self, public_function):
        html = (
            "<table><thead><tr><th>Company Name</th></tr></thead>"
            "<tbody><tr><td>Missing Ticker Co</td></tr></tbody></table>"
        )
        with (
            patch(
                "app.services.crawler_earnings.crawler_core.fetch_multi_webpages_content_playwright",
                new_callable=AsyncMock,
                return_value=[html],
            ),
            pytest.raises(ValueError),
        ):
            asyncio.run(public_function())

    @pytest.mark.parametrize(
        (
            "public_function",
            "crawler_target",
            "index_name",
            "member_symbol",
            "later_symbol",
            "lookahead_days",
            "currency",
        ),
        [
            (
                events_earnings.get_asx_upcoming_earnings_events,
                "app.services.events_earnings.services_crawler_earnings.scrape_earnings_asx",
                "ASX20",
                "ASX:CBA",
                "ASX:WBC",
                14,
                "AUD",
            ),
            (
                events_earnings.get_us_upcoming_earnings_events,
                "app.services.events_earnings.services_crawler_earnings.scrape_earnings_us",
                "NASDAQ100",
                "NASDAQ:AAPL",
                "NASDAQ:MSFT",
                7,
                "USD",
            ),
        ],
        ids=["asx", "us"],
    )
    def test_index_filter_preserves_the_market_date_window(
        self,
        public_function,
        crawler_target,
        index_name,
        member_symbol,
        later_symbol,
        lookahead_days,
        currency,
    ):
        store = _store_with_index(index_name, member_symbol, later_symbol)
        boundary_date = datetime.date(2026, 11, 16) + datetime.timedelta(days=lookahead_days)
        exchange, ticker = member_symbol.split(":")
        later_exchange, later_ticker = later_symbol.split(":")
        raw_data = _earnings_frame(
            [
                _earnings_row(
                    ticker,
                    "Boundary Company",
                    exchange=exchange,
                    currency=currency,
                    announcement_date=boundary_date.isoformat(),
                ),
                _earnings_row(
                    later_ticker,
                    "Later Company",
                    exchange=later_exchange,
                    currency=currency,
                    announcement_date=(boundary_date + datetime.timedelta(days=1)).isoformat(),
                ),
            ]
        )

        async def crawler_boundary(end_date):
            return raw_data[raw_data["Announcement Date"] <= end_date.isoformat()]

        with (
            patch("app.services.events_earnings.datetime.datetime", _FixedDateTime),
            patch.object(services_market, "market_indices", store),
            patch(crawler_target, new=crawler_boundary),
        ):
            unfiltered_events = asyncio.run(public_function())
            filtered_events = asyncio.run(public_function(index_name.lower()))

        assert [item.symbol for item in unfiltered_events] == [member_symbol]
        assert [item.symbol for item in filtered_events] == [member_symbol]

    @pytest.mark.parametrize(
        ("public_function", "index_name", "symbols", "timezone_name"),
        [
            (
                events_earnings.get_asx_upcoming_earnings_events,
                "ASX20",
                ["ASX:WBC", "ASX:CBA"],
                "Australia/Sydney",
            ),
            (
                events_earnings.get_us_upcoming_earnings_events,
                "SP500",
                ["NYSE:IBM", "NASDAQ:AAPL"],
                "America/New_York",
            ),
        ],
        ids=["asx", "us"],
    )
    def test_crawled_rows_reach_public_event_models(self, public_function, index_name, symbols, timezone_name):
        first_ticker, second_ticker = [symbol.split(":")[-1] for symbol in symbols]
        html = (
            "<table><thead><tr><th>Name</th><th>Company Name</th>"
            "<th>EPS / Forecast</th><th>Revenue / Forecast</th></tr></thead><tbody>"
            f"<tr><td>{first_ticker}</td><td>Named Company</td><td>N/A / -$2.5</td><td>$1.001B /</td></tr>"
            f"<tr><td>{second_ticker}</td><td></td><td>-$1.25 / N/A</td><td>N/A / $2B</td></tr>"
            "<tr><td>OUTSIDE</td><td>Outside Company</td><td></td><td></td></tr>"
            "</tbody></table>"
        )
        store = _store_with_index(index_name, *symbols)

        async def fetch_pages(urls, **_kwargs):
            return [html] + [None] * (len(urls) - 1)

        with (
            patch("app.services.events_earnings.datetime.datetime", _FixedDateTime),
            patch.object(services_market, "market_indices", store),
            patch(
                "app.services.crawler_earnings.crawler_core.fetch_multi_webpages_content_playwright",
                new=fetch_pages,
            ),
        ):
            result = asyncio.run(public_function(index_name.lower()))

        assert [event.symbol for event in result] == symbols
        assert [event.company_name for event in result] == ["Named Company", second_ticker]
        expected_date = datetime.datetime(2026, 11, 16, tzinfo=zoneinfo.ZoneInfo(timezone_name))
        assert all(event.timestamp_str == expected_date.isoformat(sep=" ", timespec="seconds") for event in result)
        assert all(event.timestamp == int(expected_date.timestamp()) for event in result)
        assert all(event.event_category == "earnings" for event in result)
        assert all(event.status == "estimated" and event.report_period == "N/A" for event in result)
        assert len({event.link for event in result}) == len(result)
        currency = "AUD" if timezone_name == "Australia/Sydney" else "USD"
        assert [
            (event.market_cap, event.eps, event.eps_forecast, event.revenue, event.revenue_forecast, event.currency)
            for event in result
        ] == [
            (0, 0.0, -2.5, 1_001_000_000, 0, currency),
            (0, -1.25, 0.0, 0, 2_000_000_000, currency),
        ]


class TestDividendEvents:
    @pytest.mark.parametrize(
        ("public_function", "crawler_target", "invalid_index"),
        [
            (
                events_div.get_asx_upcoming_dividends_events,
                "app.services.events_div.services_crawler_div.scrape_dividends_asx",
                "SP500",
            ),
            (
                events_div.get_us_upcoming_dividends_events,
                "app.services.events_div.services_crawler_div.scrape_dividends_us",
                "ASX200",
            ),
            (
                events_div.get_vn_upcoming_dividends_events,
                "app.services.events_div.services_crawler_div.scrape_dividends_vn",
                "NASDAQ100",
            ),
        ],
    )
    def test_invalid_index_returns_empty(self, public_function, crawler_target, invalid_index):
        with patch(crawler_target, new_callable=AsyncMock, return_value=pd.DataFrame()):
            result = asyncio.run(public_function(invalid_index))

        assert result == []

    def test_asx_category_policy_and_source_order(self):
        raw_data = _dividend_frame(
            [
                _dividend_row("FND", "Alpha Fund"),
                _dividend_row("TRU", "Beta TRUST"),
                _dividend_row("REI", "Gamma reit"),
                _dividend_row("ETF", "Delta ETF"),
                _dividend_row("PRP", "Epsilon Property Group"),
                _dividend_row("ORD", "Ordinary Holdings"),
            ]
        )

        with patch(
            "app.services.events_div.services_crawler_div.scrape_dividends_asx",
            new_callable=AsyncMock,
            return_value=raw_data,
        ):
            result = asyncio.run(events_div.get_asx_upcoming_dividends_events())

        assert [dividend.symbol for dividend in result] == [
            "ASX:FND",
            "ASX:TRU",
            "ASX:REI",
            "ASX:ETF",
            "ASX:PRP",
            "ASX:ORD",
        ]
        assert [dividend.event_category for dividend in result] == [
            "distribution",
            "distribution",
            "distribution",
            "distribution",
            "distribution",
            "dividend",
        ]
        first = result[0]
        assert first.company_name == "Alpha Fund"
        assert first.timestamp_str.startswith("2026-11-20 00:00:00")
        assert first.payment_date.startswith("2026-12-15 00:00:00")
        assert first.amount == 1.5
        assert first.dividend_yield == 0.03
        assert first.currency == "AUD"
        assert first.source_name == "ASX"
        assert first.status == "declared"
        assert urlparse(first.link).hostname == "www.asx.com.au"

    def test_missing_crawled_numeric_fields_are_zero_in_events(self):
        html = (
            "<table><thead><tr><th>Name</th><th>Company</th><th>Dividend Amount</th></tr></thead>"
            "<tbody><tr><td>AAA</td><td>Alpha Ltd</td><td>AU$0.25</td></tr></tbody></table>"
        )

        with patch(
            "app.services.crawler_div.crawler_core.fetch_multi_webpages_content_playwright",
            new_callable=AsyncMock,
            return_value=[html],
        ):
            result = asyncio.run(events_div.get_asx_upcoming_dividends_events())

        assert len(result) == 1
        assert result[0].amount == 0.25
        assert result[0].dividend_yield == 0.0
        assert result[0].payment_date is None

    def test_us_events_omit_unknown_exchanges_and_preserve_order(self):
        raw_data = _dividend_frame(
            [
                _dividend_row(
                    "AAPL",
                    "Apple Inc.",
                    exchange="NASDAQ",
                    currency="USD",
                    payment_date=None,
                ),
                _dividend_row(
                    "UNKNOWN",
                    "Unknown Co",
                    exchange="N/A",
                    currency="USD",
                    payment_date=None,
                ),
                _dividend_row(
                    "MSFT",
                    "Microsoft Corp.",
                    exchange="NYSE",
                    currency="USD",
                    payment_date=None,
                ),
            ]
        )

        with patch(
            "app.services.events_div.services_crawler_div.scrape_dividends_us",
            new_callable=AsyncMock,
            return_value=raw_data,
        ):
            result = asyncio.run(events_div.get_us_upcoming_dividends_events())

        assert [dividend.symbol for dividend in result] == ["NASDAQ:AAPL", "NYSE:MSFT"]
        assert [dividend.event_category for dividend in result] == ["dividend", "dividend"]
        assert result[0].payment_date is None
        assert all(dividend.timestamp_str.endswith("-05:00") for dividend in result)
        assert all(urlparse(dividend.link).hostname == "stockanalysis.com" for dividend in result)

    def test_vn_events_are_always_cash_dividends(self):
        raw_data = _dividend_frame(
            [
                _dividend_row(
                    "VNM",
                    "VNM PROPERTY FUND",
                    exchange="HOSE",
                    currency="VND",
                )
            ]
        )

        with patch(
            "app.services.events_div.services_crawler_div.scrape_dividends_vn",
            new_callable=AsyncMock,
            return_value=raw_data,
        ):
            result = asyncio.run(events_div.get_vn_upcoming_dividends_events())

        assert len(result) == 1
        dividend = result[0]
        assert dividend.symbol == "HOSE:VNM"
        assert dividend.event_category == "dividend"
        assert dividend.source_name == "VietStock"
        assert dividend.currency == "VND"
        assert dividend.timestamp_str.endswith("+07:00")
        assert dividend.payment_date.endswith("+07:00")
        assert urlparse(dividend.link).hostname == "finance.vietstock.vn"

    @pytest.mark.parametrize(
        ("public_function", "crawler_target", "index_name", "member_symbol", "row"),
        [
            (
                events_div.get_asx_upcoming_dividends_events,
                "app.services.events_div.services_crawler_div.scrape_dividends_asx",
                "ASX20",
                "ASX:CBA",
                _dividend_row("CBA", "Commonwealth Bank"),
            ),
            (
                events_div.get_us_upcoming_dividends_events,
                "app.services.events_div.services_crawler_div.scrape_dividends_us",
                "SP500",
                "NASDAQ:AAPL",
                _dividend_row("AAPL", "Apple Inc.", exchange="NASDAQ", currency="USD"),
            ),
            (
                events_div.get_vn_upcoming_dividends_events,
                "app.services.events_div.services_crawler_div.scrape_dividends_vn",
                "VN30",
                "HOSE:VNM",
                _dividend_row("VNM", "Vietnam Dairy", exchange="HOSE", currency="VND"),
            ),
        ],
        ids=["asx", "us", "vn"],
    )
    def test_index_filters_are_case_insensitive(
        self,
        public_function,
        crawler_target,
        index_name,
        member_symbol,
        row,
    ):
        store = _store_with_index(index_name, member_symbol)
        raw_data = _dividend_frame([row])

        with (
            patch.object(services_market, "market_indices", store),
            patch(crawler_target, new_callable=AsyncMock, return_value=raw_data),
        ):
            result = asyncio.run(public_function(index_name.lower()))

        assert [dividend.symbol for dividend in result] == [member_symbol]

    @pytest.mark.parametrize(
        ("public_function", "crawler_target"),
        [
            (
                events_div.get_asx_upcoming_dividends_events,
                "app.services.events_div.services_crawler_div.scrape_dividends_asx",
            ),
            (
                events_div.get_us_upcoming_dividends_events,
                "app.services.events_div.services_crawler_div.scrape_dividends_us",
            ),
            (
                events_div.get_vn_upcoming_dividends_events,
                "app.services.events_div.services_crawler_div.scrape_dividends_vn",
            ),
        ],
    )
    def test_empty_crawler_frame_returns_no_events(self, public_function, crawler_target):
        with patch(crawler_target, new_callable=AsyncMock, return_value=pd.DataFrame()):
            assert asyncio.run(public_function()) == []


@pytest.mark.parametrize(
    ("public_function", "crawler_target", "raw_data", "expected_symbols"),
    [
        (
            events_earnings.get_asx_upcoming_earnings_events,
            "app.services.events_earnings.services_crawler_earnings.scrape_earnings_asx",
            _earnings_frame(
                [
                    _earnings_row("BHP", "BHP", announcement_date="2026-11-19"),
                    _earnings_row("CBA", "Commonwealth Bank"),
                ]
            ),
            ["ASX:BHP", "ASX:CBA"],
        ),
        (
            events_earnings.get_us_upcoming_earnings_events,
            "app.services.events_earnings.services_crawler_earnings.scrape_earnings_us",
            _earnings_frame(
                [
                    _earnings_row("MSFT", "Microsoft", exchange="NYSE", currency="USD", announcement_date="2026-11-19"),
                    _earnings_row("AAPL", "Apple Inc.", exchange="NASDAQ", currency="USD"),
                ]
            ),
            ["NYSE:MSFT", "NASDAQ:AAPL"],
        ),
        (
            events_div.get_asx_upcoming_dividends_events,
            "app.services.events_div.services_crawler_div.scrape_dividends_asx",
            _dividend_frame(
                [
                    _dividend_row("BHP", "BHP"),
                    _dividend_row("CBA", "Commonwealth Bank"),
                ]
            ),
            ["ASX:BHP", "ASX:CBA"],
        ),
        (
            events_div.get_us_upcoming_dividends_events,
            "app.services.events_div.services_crawler_div.scrape_dividends_us",
            _dividend_frame(
                [
                    _dividend_row("MSFT", "Microsoft", exchange="NYSE", currency="USD"),
                    _dividend_row("AAPL", "Apple Inc.", exchange="NASDAQ", currency="USD"),
                ]
            ),
            ["NYSE:MSFT", "NASDAQ:AAPL"],
        ),
        (
            events_div.get_vn_upcoming_dividends_events,
            "app.services.events_div.services_crawler_div.scrape_dividends_vn",
            _dividend_frame(
                [
                    _dividend_row("VNM", "Vietnam Dairy", exchange="HOSE", currency="VND"),
                    _dividend_row("FPT", "FPT Corporation", exchange="HOSE", currency="VND"),
                ]
            ),
            ["HOSE:VNM", "HOSE:FPT"],
        ),
    ],
    ids=["asx-earnings", "us-earnings", "asx-dividend", "us-dividend", "vn-dividend"],
)
def test_event_functions_preserve_source_order(
    public_function,
    crawler_target,
    raw_data,
    expected_symbols,
):
    with patch(crawler_target, new_callable=AsyncMock, return_value=raw_data):
        result = asyncio.run(public_function())

    assert [item.symbol for item in result] == expected_symbols


@pytest.mark.parametrize(
    ("public_function", "crawler_target", "index_name", "raw_data"),
    [
        (
            events_earnings.get_asx_upcoming_earnings_events,
            "app.services.events_earnings.services_crawler_earnings.scrape_earnings_asx",
            "ASX20",
            _earnings_frame([_earnings_row("CBA", "Commonwealth Bank")]),
        ),
        (
            events_earnings.get_us_upcoming_earnings_events,
            "app.services.events_earnings.services_crawler_earnings.scrape_earnings_us",
            "NASDAQ100",
            _earnings_frame([_earnings_row("AAPL", "Apple Inc.", exchange="NASDAQ", currency="USD")]),
        ),
        (
            events_div.get_asx_upcoming_dividends_events,
            "app.services.events_div.services_crawler_div.scrape_dividends_asx",
            "ASX20",
            _dividend_frame([_dividend_row("CBA", "Commonwealth Bank")]),
        ),
        (
            events_div.get_us_upcoming_dividends_events,
            "app.services.events_div.services_crawler_div.scrape_dividends_us",
            "SP500",
            _dividend_frame([_dividend_row("AAPL", "Apple Inc.", exchange="NASDAQ", currency="USD")]),
        ),
        (
            events_div.get_vn_upcoming_dividends_events,
            "app.services.events_div.services_crawler_div.scrape_dividends_vn",
            "VN30",
            _dividend_frame([_dividend_row("VNM", "Vietnam Dairy", exchange="HOSE", currency="VND")]),
        ),
    ],
    ids=["asx-earnings", "us-earnings", "asx-dividend", "us-dividend", "vn-dividend"],
)
def test_loaded_index_without_matching_constituent_returns_empty(
    public_function,
    crawler_target,
    index_name,
    raw_data,
):
    loaded_empty_store = _store_with_index(index_name)

    with (
        patch.object(services_market, "market_indices", loaded_empty_store),
        patch(crawler_target, new_callable=AsyncMock, return_value=raw_data),
    ):
        result = asyncio.run(public_function(index_name))

    assert result == []


@pytest.mark.parametrize(
    ("public_function", "crawler_target", "index_name", "raw_data"),
    [
        (
            events_earnings.get_asx_upcoming_earnings_events,
            "app.services.events_earnings.services_crawler_earnings.scrape_earnings_asx",
            "ASX20",
            _earnings_frame([_earnings_row("CBA", "Commonwealth Bank")]),
        ),
        (
            events_earnings.get_us_upcoming_earnings_events,
            "app.services.events_earnings.services_crawler_earnings.scrape_earnings_us",
            "NASDAQ100",
            _earnings_frame([_earnings_row("AAPL", "Apple Inc.", exchange="NASDAQ", currency="USD")]),
        ),
        (
            events_div.get_asx_upcoming_dividends_events,
            "app.services.events_div.services_crawler_div.scrape_dividends_asx",
            "ASX20",
            _dividend_frame([_dividend_row("CBA", "Commonwealth Bank")]),
        ),
        (
            events_div.get_us_upcoming_dividends_events,
            "app.services.events_div.services_crawler_div.scrape_dividends_us",
            "SP500",
            _dividend_frame([_dividend_row("AAPL", "Apple Inc.", exchange="NASDAQ", currency="USD")]),
        ),
        (
            events_div.get_vn_upcoming_dividends_events,
            "app.services.events_div.services_crawler_div.scrape_dividends_vn",
            "VN30",
            _dividend_frame([_dividend_row("VNM", "Vietnam Dairy", exchange="HOSE", currency="VND")]),
        ),
    ],
    ids=["asx-earnings", "us-earnings", "asx-dividend", "us-dividend", "vn-dividend"],
)
def test_supported_but_unloaded_index_raises_key_error(
    public_function,
    crawler_target,
    index_name,
    raw_data,
):
    empty_store = services_market.MarketIndexStore()

    with (
        patch.object(services_market, "market_indices", empty_store),
        patch(crawler_target, new_callable=AsyncMock, return_value=raw_data),
        pytest.raises(KeyError),
    ):
        asyncio.run(public_function(index_name))


@pytest.mark.parametrize(
    ("public_function", "crawler_target", "raw_data"),
    [
        (
            events_earnings.get_asx_upcoming_earnings_events,
            "app.services.events_earnings.services_crawler_earnings.scrape_earnings_asx",
            _earnings_frame([_earnings_row("CBA", "Commonwealth Bank", announcement_date="not-a-date")]),
        ),
        (
            events_earnings.get_us_upcoming_earnings_events,
            "app.services.events_earnings.services_crawler_earnings.scrape_earnings_us",
            _earnings_frame(
                [_earnings_row("AAPL", "Apple Inc.", exchange="NASDAQ", currency="USD", announcement_date="not-a-date")]
            ),
        ),
        (
            events_div.get_asx_upcoming_dividends_events,
            "app.services.events_div.services_crawler_div.scrape_dividends_asx",
            _dividend_frame([_dividend_row("CBA", "Commonwealth Bank", ex_date="not-a-date")]),
        ),
        (
            events_div.get_us_upcoming_dividends_events,
            "app.services.events_div.services_crawler_div.scrape_dividends_us",
            _dividend_frame(
                [
                    _dividend_row(
                        "AAPL",
                        "Apple Inc.",
                        exchange="NASDAQ",
                        currency="USD",
                        ex_date="not-a-date",
                    )
                ]
            ),
        ),
        (
            events_div.get_vn_upcoming_dividends_events,
            "app.services.events_div.services_crawler_div.scrape_dividends_vn",
            _dividend_frame(
                [
                    _dividend_row(
                        "VNM",
                        "Vietnam Dairy",
                        exchange="HOSE",
                        currency="VND",
                        ex_date="not-a-date",
                    )
                ]
            ),
        ),
    ],
    ids=["asx-earnings", "us-earnings", "asx-dividend", "us-dividend", "vn-dividend"],
)
def test_invalid_source_date_is_rejected(public_function, crawler_target, raw_data):
    with (
        patch(crawler_target, new_callable=AsyncMock, return_value=raw_data),
        pytest.raises(ValueError),
    ):
        asyncio.run(public_function())


class FakeTicker:
    def __init__(self, info, history=None, history_error=None):
        self.info = info
        self._history = history
        self._history_error = history_error

    def history(self, **_kwargs):
        if self._history_error is not None:
            raise self._history_error
        return self._history.copy()


def _history_frame(*, rows=500, include_dividends=True, dividend_positions=None):
    index = pd.date_range("2025-01-01", periods=rows, freq="D", tz="America/New_York")
    close = pd.Series(100.0, index=index)
    dividends = pd.Series(0.0, index=index)
    if include_dividends:
        positions = dividend_positions if dividend_positions is not None else (100, 200, 300, 400)
        for position in positions:
            if position + 2 < rows:
                close.iloc[position] = 98.0
                close.iloc[position + 1] = 99.0
                close.iloc[position + 2] = 100.5
                dividends.iloc[position] = 2.0
    return pd.DataFrame(
        {
            "Open": close,
            "High": close + 1.0,
            "Low": close - 1.0,
            "Close": close,
            "Volume": 1_000_000,
            "Dividends": dividends,
        },
        index=index,
    )


def _ticker_info(**overrides):
    info = {
        "quoteType": "EQUITY",
        "regularMarketPrice": 120.0,
        "symbol": "TEST",
        "exchange": "TEST",
        "longName": "Test Company",
        "beta": 1.1,
    }
    info.update(overrides)
    return info


class TestAnalyseDividendEvent:
    @pytest.mark.parametrize("blocked_access", ["info", "history"])
    def test_market_data_access_does_not_block_event_loop(self, blocked_access):
        async def run_analysis():
            loop = asyncio.get_running_loop()
            access_started = asyncio.Event()
            release_access = threading.Event()
            ticker = FakeTicker(_ticker_info(), _history_frame())

            def block_access():
                loop.call_soon_threadsafe(access_started.set)
                if not release_access.wait(timeout=5):
                    raise TimeoutError("Market-data access blocked the event loop")

            class BlockingTicker:
                @property
                def info(self):
                    if blocked_access == "info":
                        block_access()
                    return ticker.info

                def history(self, **kwargs):
                    if blocked_access == "history":
                        block_access()
                    return ticker.history(**kwargs)

            with patch(
                "app.services.events_div.yf.Ticker",
                return_value=FakeTicker({}, _history_frame()),
            ):
                task = asyncio.create_task(
                    events_div.analyse_dividend_event(
                        ticker=BlockingTicker(),
                        symbol="TEST",
                        ex_date="2026-11-20",
                        div_amount=2.5,
                    )
                )
                try:
                    await asyncio.wait_for(access_started.wait(), timeout=5)
                finally:
                    release_access.set()
                    result = await task
            return result

        result = asyncio.run(run_analysis())

        assert result is not None
        assert result.num_samples == 4

    def test_returns_none_for_unsupported_quote_type(self):
        ticker = FakeTicker(_ticker_info(quoteType="CURRENCY"), _history_frame())

        result = asyncio.run(
            events_div.analyse_dividend_event(
                ticker=ticker,
                symbol="TEST",
                ex_date="2026-11-20",
                div_amount=2.5,
            )
        )

        assert result is None

    @pytest.mark.parametrize(
        ("info", "history"),
        [
            (_ticker_info(regularMarketPrice=0), _history_frame()),
            (_ticker_info(), _history_frame(rows=50)),
            (_ticker_info(), _history_frame(include_dividends=False)),
        ],
        ids=["missing-price", "insufficient-history", "no-past-dividends"],
    )
    def test_returns_none_for_insufficient_analysis_data(self, info, history):
        ticker = FakeTicker(info, history)

        result = asyncio.run(
            events_div.analyse_dividend_event(
                ticker=ticker,
                symbol="TEST",
                ex_date="2026-11-20",
                div_amount=2.5,
            )
        )

        assert result is None

    def test_rejects_invalid_ex_dividend_date(self):
        ticker = FakeTicker(_ticker_info(), _history_frame())

        with pytest.raises(ValueError):
            asyncio.run(
                events_div.analyse_dividend_event(
                    ticker=ticker,
                    symbol="TEST",
                    ex_date="20/11/2026",
                    div_amount=2.5,
                )
            )

    @pytest.mark.parametrize("column", ["Open", "High", "Low", "Close", "Volume", "Dividends"])
    def test_missing_required_history_column_is_surfaced(self, column):
        history = _history_frame().drop(columns=[column])
        ticker = FakeTicker(_ticker_info(), history)

        with pytest.raises(KeyError):
            asyncio.run(
                events_div.analyse_dividend_event(
                    ticker=ticker,
                    symbol="TEST",
                    ex_date="2026-11-20",
                    div_amount=2.5,
                )
            )

    def test_exactly_ninety_completed_history_rows_are_supported(self):
        completed_history = _history_frame(rows=90, dividend_positions=(20, 60))
        current_observation = completed_history.iloc[[-1]].copy()
        current_observation.index = pd.DatetimeIndex([completed_history.index[-1] + pd.Timedelta(days=1)])
        history = pd.concat([completed_history, current_observation])
        ticker = FakeTicker(_ticker_info(), history)

        with patch(
            "app.services.events_div.yf.Ticker",
            return_value=FakeTicker({}, _history_frame()),
        ):
            result = asyncio.run(
                events_div.analyse_dividend_event(
                    ticker=ticker,
                    symbol="TEST",
                    ex_date="2026-11-20",
                    div_amount=2.5,
                )
            )

        assert result is not None
        assert result.num_samples == 2

    @pytest.mark.parametrize(
        ("quote_type", "symbol"),
        [
            ("ETF", "TEST-ETF"),
            ("MUTUALFUND", "TEST-FUND"),
        ],
    )
    def test_supported_fund_types_return_analysis(self, quote_type, symbol):
        ticker = FakeTicker(
            _ticker_info(quoteType=quote_type, symbol=symbol),
            _history_frame(),
        )

        with patch(
            "app.services.events_div.yf.Ticker",
            return_value=FakeTicker({}, _history_frame()),
        ):
            result = asyncio.run(
                events_div.analyse_dividend_event(
                    ticker=ticker,
                    symbol=symbol,
                    ex_date="2026-11-20",
                    div_amount=2.5,
                )
            )

        assert result is not None
        assert result.symbol == symbol
        assert math.isclose(result.div_yield, 2.5 / 120.0)

    def test_timezone_failure_is_surfaced(self):
        ticker = FakeTicker(_ticker_info(), _history_frame())

        with (
            patch(
                "app.services.events_div.yfutils.tz_from_yf_ticker",
                side_effect=zoneinfo.ZoneInfoNotFoundError("missing timezone"),
            ),
            pytest.raises(zoneinfo.ZoneInfoNotFoundError),
        ):
            asyncio.run(
                events_div.analyse_dividend_event(
                    ticker=ticker,
                    symbol="TEST",
                    ex_date="2026-11-20",
                    div_amount=2.5,
                )
            )

    def test_provider_failure_is_surfaced(self):
        ticker = FakeTicker(
            _ticker_info(),
            _history_frame(),
            history_error=RuntimeError("provider unavailable"),
        )

        with pytest.raises(RuntimeError):
            asyncio.run(
                events_div.analyse_dividend_event(
                    ticker=ticker,
                    symbol="TEST",
                    ex_date="2026-11-20",
                    div_amount=2.5,
                )
            )

    def test_returns_documented_analysis_metrics(self):
        ticker = FakeTicker(_ticker_info(), _history_frame())

        with patch(
            "app.services.events_div.yf.Ticker",
            return_value=FakeTicker(_ticker_info(), _history_frame()),
        ):
            result = asyncio.run(
                events_div.analyse_dividend_event(
                    ticker=ticker,
                    symbol="TEST",
                    ex_date="2026-11-20",
                    div_amount=2.5,
                )
            )

        assert result is not None
        assert result.symbol == "TEST"
        assert result.exchange == "TEST"
        assert result.company_name == "Test Company"
        assert result.price == 120.0
        assert result.div_amount == 2.5
        assert math.isclose(result.div_yield, 2.5 / 120.0)
        assert result.num_samples == 4
        assert math.isclose(result.drop_price_min, 1.25)
        assert math.isclose(result.drop_price_max, 1.25)
        assert result.beta == 1.1
