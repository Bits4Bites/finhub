"""Unit tests for app.services.event module."""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from app.services.event import (
    _calc_end_date_to_fetch_events,
    get_asx_upcoming_dividends_events,
    get_asx_upcoming_earnings_events,
    get_us_upcoming_dividends_events,
    get_us_upcoming_earnings_events,
    get_vn_upcoming_dividends_events,
)

# ===========================================================================
# calc_end_date_to_fetch_events
# ===========================================================================


class TestCalcEndDateToFetchEvents:
    def test_dividend_with_index_returns_14_days(self):
        tz = ZoneInfo("Australia/Sydney")
        result = _calc_end_date_to_fetch_events(event_type="DIVIDEND", tz=tz, index="ASX200")
        today = datetime.now(tz).date()
        assert result == today + timedelta(days=14)

    def test_earnings_with_index_returns_10_days(self):
        tz = ZoneInfo("America/New_York")
        result = _calc_end_date_to_fetch_events(event_type="EARNINGS", tz=tz, index="SP500")
        today = datetime.now(tz).date()
        assert result == today + timedelta(days=10)

    def test_no_index_returns_7_days(self):
        tz = ZoneInfo("Australia/Sydney")
        result = _calc_end_date_to_fetch_events(event_type="DIVIDEND", tz=tz, index="")
        today = datetime.now(tz).date()
        assert result == today + timedelta(days=7)

    def test_no_index_default_returns_7_days(self):
        tz = ZoneInfo("America/New_York")
        result = _calc_end_date_to_fetch_events(event_type="EARNINGS", tz=tz)
        today = datetime.now(tz).date()
        assert result == today + timedelta(days=7)

    def test_event_type_case_insensitive(self):
        tz = ZoneInfo("Australia/Sydney")
        result = _calc_end_date_to_fetch_events(event_type="earnings", tz=tz, index="ASX200")
        today = datetime.now(tz).date()
        assert result == today + timedelta(days=10)


# ===========================================================================
# get_asx_upcoming_dividends_events
# ===========================================================================


class TestAsxUpcomingDividendsEvents:
    @patch("app.services.event._get_upcoming_dividends_events", new_callable=AsyncMock, return_value=[])
    def test_invalid_index_returns_empty_without_calling_service(self, mock_get_events):
        result = asyncio.run(get_asx_upcoming_dividends_events("INVALID_INDEX"))
        assert result == []
        mock_get_events.assert_not_called()

    @patch("app.services.event._get_upcoming_dividends_events", new_callable=AsyncMock, return_value=[])
    def test_valid_index_calls_service(self, mock_get_events):
        result = asyncio.run(get_asx_upcoming_dividends_events("ASX200"))
        assert result == []
        mock_get_events.assert_called_once()

    @patch("app.services.event._get_upcoming_dividends_events", new_callable=AsyncMock, return_value=[])
    def test_no_index_calls_service(self, mock_get_events):
        result = asyncio.run(get_asx_upcoming_dividends_events(""))
        assert result == []
        mock_get_events.assert_called_once()

    @patch("app.services.event._get_upcoming_dividends_events", new_callable=AsyncMock, return_value=[])
    def test_case_insensitive_index(self, mock_get_events):
        result = asyncio.run(get_asx_upcoming_dividends_events("asx50"))
        assert result == []
        mock_get_events.assert_called_once()

    @patch("app.services.event.asset_utils.is_in_index", return_value=True)
    @patch("app.services.event._get_upcoming_dividends_events", new_callable=AsyncMock)
    def test_filters_by_index_and_adds_link(self, mock_get_events, mock_is_in_index):
        from app.models.event import UpcomingDividendEvent

        mock_event = UpcomingDividendEvent(
            symbol="ASX:CBA", exchange="ASX", company_name="CBA", payment_date="2026-02-01"
        )
        mock_get_events.return_value = [mock_event]

        result = asyncio.run(get_asx_upcoming_dividends_events("ASX200"))
        assert len(result) == 1
        assert "asx.com.au" in result[0].link


# ===========================================================================
# get_us_upcoming_dividends_events
# ===========================================================================


class TestUsUpcomingDividendsEvents:
    @patch("app.services.event._get_upcoming_dividends_events", new_callable=AsyncMock, return_value=[])
    def test_invalid_index_returns_empty(self, mock_get_events):
        result = asyncio.run(get_us_upcoming_dividends_events("INVALID"))
        assert result == []
        mock_get_events.assert_not_called()

    @patch("app.services.event._get_upcoming_dividends_events", new_callable=AsyncMock, return_value=[])
    def test_valid_index_sp500(self, mock_get_events):
        result = asyncio.run(get_us_upcoming_dividends_events("SP500"))
        assert result == []
        mock_get_events.assert_called_once()

    @patch("app.services.event._get_upcoming_dividends_events", new_callable=AsyncMock, return_value=[])
    def test_valid_index_nasdaq100(self, mock_get_events):
        result = asyncio.run(get_us_upcoming_dividends_events("NASDAQ100"))
        assert result == []
        mock_get_events.assert_called_once()

    @patch("app.services.event.asset_utils.is_in_index", return_value=True)
    @patch("app.services.event._get_upcoming_dividends_events", new_callable=AsyncMock)
    def test_adds_stockanalysis_link(self, mock_get_events, mock_is_in_index):
        from app.models.event import UpcomingDividendEvent

        mock_event = UpcomingDividendEvent(
            symbol="NASDAQ:AAPL", exchange="NASDAQ", company_name="Apple", payment_date="2026-02-01"
        )
        mock_get_events.return_value = [mock_event]

        result = asyncio.run(get_us_upcoming_dividends_events("NASDAQ100"))
        assert len(result) == 1
        assert "stockanalysis.com" in result[0].link
        assert "aapl" in result[0].link


# ===========================================================================
# get_vn_upcoming_dividends_events
# ===========================================================================


class TestVnUpcomingDividendsEvents:
    @patch("app.services.event._get_upcoming_dividends_events", new_callable=AsyncMock, return_value=[])
    def test_invalid_index_returns_empty(self, mock_get_events):
        result = asyncio.run(get_vn_upcoming_dividends_events("INVALID"))
        assert result == []
        mock_get_events.assert_not_called()

    @patch("app.services.event._get_upcoming_dividends_events", new_callable=AsyncMock, return_value=[])
    def test_valid_index_vn30(self, mock_get_events):
        result = asyncio.run(get_vn_upcoming_dividends_events("VN30"))
        assert result == []
        mock_get_events.assert_called_once()

    @patch("app.services.event.asset_utils.is_in_index", return_value=True)
    @patch("app.services.event._get_upcoming_dividends_events", new_callable=AsyncMock)
    def test_adds_vietstock_link(self, mock_get_events, mock_is_in_index):
        from app.models.event import UpcomingDividendEvent

        mock_event = UpcomingDividendEvent(
            symbol="HOSE:VNM", exchange="HOSE", company_name="VNM", payment_date="2026-02-01"
        )
        mock_get_events.return_value = [mock_event]

        result = asyncio.run(get_vn_upcoming_dividends_events("VN30"))
        assert len(result) == 1
        assert "vietstock.vn" in result[0].link


# ===========================================================================
# get_asx_upcoming_earnings_events
# ===========================================================================


class TestAsxUpcomingEarningsEvents:
    @patch("app.services.event._get_upcoming_earnings_events", new_callable=AsyncMock, return_value=[])
    def test_invalid_index_returns_empty(self, mock_get_events):
        result = asyncio.run(get_asx_upcoming_earnings_events("INVALID"))
        assert result == []
        mock_get_events.assert_not_called()

    @patch("app.services.event._get_upcoming_earnings_events", new_callable=AsyncMock, return_value=[])
    def test_valid_index(self, mock_get_events):
        result = asyncio.run(get_asx_upcoming_earnings_events("ASX300"))
        assert result == []
        mock_get_events.assert_called_once()

    @patch("app.services.event.asset_utils.is_in_index", return_value=True)
    @patch("app.services.event._get_upcoming_earnings_events", new_callable=AsyncMock)
    def test_adds_tipranks_link(self, mock_get_events, mock_is_in_index):
        from app.models.event import UpcomingEarningsEvent

        mock_event = UpcomingEarningsEvent(symbol="ASX:CBA", exchange="ASX", company_name="CBA")
        mock_get_events.return_value = [mock_event]

        result = asyncio.run(get_asx_upcoming_earnings_events("ASX200"))
        assert len(result) == 1
        assert "tipranks.com" in result[0].link
        assert "au:cba" in result[0].link


# ===========================================================================
# get_us_upcoming_earnings_events
# ===========================================================================


class TestUsUpcomingEarningsEvents:
    @patch("app.services.event._get_upcoming_earnings_events", new_callable=AsyncMock, return_value=[])
    def test_invalid_index_returns_empty(self, mock_get_events):
        result = asyncio.run(get_us_upcoming_earnings_events("INVALID"))
        assert result == []
        mock_get_events.assert_not_called()

    @patch("app.services.event._get_upcoming_earnings_events", new_callable=AsyncMock, return_value=[])
    def test_valid_index(self, mock_get_events):
        result = asyncio.run(get_us_upcoming_earnings_events("NASDAQ100"))
        assert result == []
        mock_get_events.assert_called_once()

    @patch("app.services.event.asset_utils.is_in_index", return_value=True)
    @patch("app.services.event._get_upcoming_earnings_events", new_callable=AsyncMock)
    def test_adds_tipranks_link(self, mock_get_events, mock_is_in_index):
        from app.models.event import UpcomingEarningsEvent

        mock_event = UpcomingEarningsEvent(symbol="NASDAQ:AAPL", exchange="NASDAQ", company_name="Apple")
        mock_get_events.return_value = [mock_event]

        result = asyncio.run(get_us_upcoming_earnings_events("SP500"))
        assert len(result) == 1
        assert "tipranks.com" in result[0].link
        assert "aapl" in result[0].link


# ===========================================================================
# get_upcoming_dividends_events (integration with crawler)
# ===========================================================================


class TestGetUpcomingDividendsEvents:
    @patch("app.services.event.services_crawler.scrape_dividends_asx", new_callable=AsyncMock)
    def test_empty_dataframe_returns_empty_list(self, mock_scrape):
        from app.services.event import _get_upcoming_dividends_events

        mock_scrape.return_value = pd.DataFrame()
        tz = ZoneInfo("Australia/Sydney")
        result = asyncio.run(_get_upcoming_dividends_events("AU", tz))
        assert result == []

    @patch("app.services.event.services_crawler.scrape_dividends_asx", new_callable=AsyncMock)
    def test_au_processes_raw_data_into_events(self, mock_scrape):
        from app.services.event import _get_upcoming_dividends_events

        raw_data = pd.DataFrame(
            {
                "Symbol": ["CBA"],
                "Exchange Name": ["ASX"],
                "Company Name": ["Commonwealth Bank"],
                "Ex-Dividend Date": ["2025-08-15"],
                "Payment Date": ["2025-09-01"],
                "Dividend Amount": ["AU$2.50"],
                "Dividend Yield": ["3.5%"],
            }
        )
        mock_scrape.return_value = raw_data
        tz = ZoneInfo("Australia/Sydney")
        default_vals = {"exchange": "ASX", "src": "ASX", "currency": "AUD", "status": "declared"}

        result = asyncio.run(_get_upcoming_dividends_events("AU", tz, default_vals=default_vals))
        assert len(result) == 1
        assert result[0].symbol == "ASX:CBA"
        assert result[0].company_name == "Commonwealth Bank"
        assert result[0].amount == 2.5
        assert result[0].event_category == "dividend"

    @patch("app.services.event.services_crawler.scrape_dividends_asx", new_callable=AsyncMock)
    def test_au_filters_low_yield(self, mock_scrape):
        from app.services.event import _get_upcoming_dividends_events

        raw_data = pd.DataFrame(
            {
                "Symbol": ["LOW", "HIGH"],
                "Exchange Name": ["ASX", "ASX"],
                "Company Name": ["Low Yield Co", "High Yield Co"],
                "Ex-Dividend Date": ["2025-08-15", "2025-08-16"],
                "Payment Date": ["2025-09-01", "2025-09-02"],
                "Dividend Amount": ["0.10", "5.00"],
                "Dividend Yield": ["0.5%", "4.0%"],
            }
        )
        mock_scrape.return_value = raw_data
        tz = ZoneInfo("Australia/Sydney")
        default_vals = {"exchange": "ASX", "src": "ASX", "currency": "AUD", "status": "declared"}

        result = asyncio.run(_get_upcoming_dividends_events("AU", tz, default_vals=default_vals))
        assert len(result) == 1
        assert result[0].symbol == "ASX:HIGH"

    @patch("app.services.event.services_crawler.scrape_dividends_asx", new_callable=AsyncMock)
    def test_au_classifies_distribution_for_trust(self, mock_scrape):
        from app.services.event import _get_upcoming_dividends_events

        raw_data = pd.DataFrame(
            {
                "Symbol": ["VAS"],
                "Exchange Name": ["ASX"],
                "Company Name": ["Vanguard Australian Shares ETF"],
                "Ex-Dividend Date": ["2025-08-15"],
                "Payment Date": ["2025-09-01"],
                "Dividend Amount": ["1.50"],
                "Dividend Yield": ["3.0%"],
            }
        )
        mock_scrape.return_value = raw_data
        tz = ZoneInfo("Australia/Sydney")
        default_vals = {"exchange": "ASX", "src": "ASX", "currency": "AUD", "status": "declared"}

        result = asyncio.run(_get_upcoming_dividends_events("AU", tz, default_vals=default_vals))
        assert len(result) == 1
        assert result[0].event_category == "distribution"

    @patch("app.services.event.services_crawler.scrape_dividends_us", new_callable=AsyncMock)
    def test_us_filters_non_major_exchanges(self, mock_scrape):
        from app.services.event import _get_upcoming_dividends_events

        raw_data = pd.DataFrame(
            {
                "Symbol": ["AAPL", "OTC1"],
                "Exchange Name": ["NASDAQ", "OTC"],
                "Company Name": ["Apple Inc.", "OTC Company"],
                "Ex-Dividend Date": ["2025-08-15", "2025-08-15"],
                "Payment Date": ["2025-09-01", "2025-09-01"],
                "Dividend Amount": ["0.96", "0.50"],
                "Dividend Yield": ["0.6%", "1.0%"],
            }
        )
        mock_scrape.return_value = raw_data
        tz = ZoneInfo("America/New_York")
        default_vals = {"src": "StockAnalysis", "currency": "USD", "status": "declared"}

        result = asyncio.run(_get_upcoming_dividends_events("US", tz, default_vals=default_vals))
        assert len(result) == 1
        assert result[0].symbol == "NASDAQ:AAPL"

    @patch("app.services.event.services_crawler.scrape_dividends_asx", new_callable=AsyncMock)
    def test_removes_url_column(self, mock_scrape):
        from app.services.event import _get_upcoming_dividends_events

        raw_data = pd.DataFrame(
            {
                "Symbol": ["BHP"],
                "Exchange Name": ["ASX"],
                "Company Name": ["BHP Group"],
                "Ex-Dividend Date": ["2025-08-15"],
                "Payment Date": ["2025-09-01"],
                "Dividend Amount": ["3.00"],
                "Dividend Yield": ["5.0%"],
                "Url": ["https://example.com"],
            }
        )
        mock_scrape.return_value = raw_data
        tz = ZoneInfo("Australia/Sydney")
        default_vals = {"exchange": "ASX", "src": "ASX", "currency": "AUD", "status": "declared"}

        result = asyncio.run(_get_upcoming_dividends_events("AU", tz, default_vals=default_vals))
        assert len(result) == 1


# ===========================================================================
# get_upcoming_earnings_events (integration with crawler)
# ===========================================================================


class TestGetUpcomingEarningsEvents:
    @patch("app.services.event.services_crawler.scrape_earnings_asx", new_callable=AsyncMock)
    def test_empty_dataframe_returns_empty_list(self, mock_scrape):
        from app.services.event import _get_upcoming_earnings_events

        mock_scrape.return_value = pd.DataFrame()
        tz = ZoneInfo("Australia/Sydney")
        result = asyncio.run(_get_upcoming_earnings_events("AU", tz))
        assert result == []

    @patch("app.services.event.services_crawler.scrape_earnings_asx", new_callable=AsyncMock)
    def test_au_processes_raw_data(self, mock_scrape):
        from app.services.event import _get_upcoming_earnings_events

        raw_data = pd.DataFrame(
            {
                "Symbol": ["CBA"],
                "Exchange Name": ["ASX"],
                "Company Name": ["Commonwealth Bank"],
                "Announcement Date": ["2025-08-15"],
            }
        )
        mock_scrape.return_value = raw_data
        tz = ZoneInfo("Australia/Sydney")
        default_vals = {"exchange": "ASX", "src": "TipRanks", "status": "estimated", "report_period": "N/A"}

        result = asyncio.run(_get_upcoming_earnings_events("AU", tz, default_vals=default_vals))
        assert len(result) == 1
        assert result[0].symbol == "ASX:CBA"
        assert result[0].company_name == "Commonwealth Bank"

    @patch("app.services.event.services_crawler.scrape_earnings_us", new_callable=AsyncMock)
    def test_us_filters_non_major_exchanges(self, mock_scrape):
        from app.services.event import _get_upcoming_earnings_events

        raw_data = pd.DataFrame(
            {
                "Symbol": ["AAPL", "PINK1"],
                "Exchange Name": ["NASDAQ", "PINK"],
                "Company Name": ["Apple Inc.", "Pink Sheets Co"],
                "Announcement Date": ["2025-08-15", "2025-08-15"],
            }
        )
        mock_scrape.return_value = raw_data
        tz = ZoneInfo("America/New_York")
        default_vals = {"src": "TipRanks", "status": "estimated", "report_period": "N/A"}

        result = asyncio.run(_get_upcoming_earnings_events("US", tz, default_vals=default_vals))
        assert len(result) == 1
        assert result[0].symbol == "NASDAQ:AAPL"


# ===========================================================================
# analyse_dividend_event
# ===========================================================================


def _make_history_df(num_days=200, base_price=100.0, div_days=None):
    """Helper to create a mock yfinance history DataFrame."""
    dates = pd.date_range("2020-01-01", periods=num_days, freq="D", tz="Australia/Sydney")
    close = np.full(num_days, base_price) + np.random.uniform(-2, 2, num_days)
    dividends = np.zeros(num_days)
    if div_days:
        for d in div_days:
            if d < num_days:
                dividends[d] = 2.0
    df = pd.DataFrame(
        {
            "Open": close - 0.5,
            "High": close + 1.0,
            "Low": close - 1.0,
            "Close": close,
            "Volume": np.full(num_days, 1_000_000),
            "Dividends": dividends,
        },
        index=dates,
    )
    return df


class TestAnalyseDividendEvent:
    @patch("app.services.event.yfutils.lookup_peer_yf_static_symbol", return_value=None)
    @patch("app.services.event.yfutils.lookup_index_yf_static_symbol", return_value=None)
    @patch("app.services.event.yf.Ticker")
    def test_returns_none_for_quote_type_none(self, mock_ticker_cls, mock_lookup_idx, mock_lookup_peer):
        from app.services.event import analyse_dividend_event

        mock_ticker_cls.return_value.info = {"quoteType": "NONE", "country": "Australia"}
        result = asyncio.run(analyse_dividend_event(symbol="ASX:CBA", ex_date="2025-08-15", div_amount=2.5))
        assert result is None

    @patch("app.services.event.yf.Ticker")
    def test_raises_for_unsupported_quote_type(self, mock_ticker_cls):
        from app.services.event import analyse_dividend_event

        mock_ticker_cls.return_value.info = {"quoteType": "CURRENCY", "country": "US"}
        try:
            asyncio.run(analyse_dividend_event(symbol="NASDAQ:AAPL", ex_date="2025-08-15", div_amount=1.0))
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "not supported" in str(e)

    @patch("app.services.event.yfutils.lookup_peer_yf_static_symbol", return_value=None)
    @patch("app.services.event.yfutils.lookup_index_yf_static_symbol", return_value=None)
    @patch("app.services.event.yf.Ticker")
    def test_returns_none_for_insufficient_history(self, mock_ticker_cls, mock_lookup_idx, mock_lookup_peer):
        from app.services.event import analyse_dividend_event

        mock_ticker = mock_ticker_cls.return_value
        mock_ticker.info = {
            "quoteType": "EQUITY",
            "regularMarketPrice": 120.0,
            "symbol": "CBA.AX",
            "fullExchangeName": "ASX",
            "longName": "Commonwealth Bank",
            "country": "Australia",
        }
        # Only 50 days of history (< 90 required)
        mock_ticker.history.return_value = _make_history_df(num_days=50)

        result = asyncio.run(analyse_dividend_event(symbol="ASX:CBA", ex_date="2025-08-15", div_amount=2.5))
        assert result is None

    @patch("app.services.event.yfutils.lookup_peer_yf_static_symbol", return_value=None)
    @patch("app.services.event.yfutils.lookup_index_yf_static_symbol", return_value=None)
    @patch("app.services.event.yf.Ticker")
    def test_returns_analysis_with_sufficient_data(self, mock_ticker_cls, mock_lookup_idx, mock_lookup_peer):
        from app.services.event import analyse_dividend_event

        mock_ticker = mock_ticker_cls.return_value
        mock_ticker.info = {
            "quoteType": "EQUITY",
            "regularMarketPrice": 120.0,
            "symbol": "CBA.AX",
            "fullExchangeName": "ASX",
            "longName": "Commonwealth Bank",
            "country": "Australia",
            "beta": 1.1,
        }
        # 500 days with dividends at day 100, 200, 300, 400
        history = _make_history_df(num_days=500, base_price=120.0, div_days=[100, 200, 300, 400])
        mock_ticker.history.return_value = history

        result = asyncio.run(analyse_dividend_event(symbol="ASX:CBA", ex_date="2025-08-15", div_amount=2.5))
        assert result is not None
        assert result.symbol == "CBA.AX"
        assert result.exchange == "ASX"
        assert result.company_name == "Commonwealth Bank"
        assert result.price == 120.0
        assert result.div_amount == 2.5
        assert result.num_samples == 4
        assert result.drop_price_min >= 0
        assert result.drop_price_max >= result.drop_price_min
        assert result.recovery_probability >= 0
        assert result.beta == 1.1
        assert result.rsi14 > 0

    @patch("app.services.event.yfutils.lookup_peer_yf_static_symbol", return_value=None)
    @patch("app.services.event.yfutils.lookup_index_yf_static_symbol", return_value=None)
    @patch("app.services.event.yf.Ticker")
    def test_uses_provided_ticker(self, mock_ticker_cls, mock_lookup_idx, mock_lookup_peer):
        from app.services.event import analyse_dividend_event

        provided_ticker = MagicMock()
        provided_ticker.info = {
            "quoteType": "EQUITY",
            "regularMarketPrice": 50.0,
            "symbol": "BHP.AX",
            "fullExchangeName": "ASX",
            "longName": "BHP Group",
            "country": "Australia",
            "beta": 0.9,
        }
        history = _make_history_df(num_days=500, base_price=50.0, div_days=[90, 180, 270, 360])
        provided_ticker.history.return_value = history

        result = asyncio.run(
            analyse_dividend_event(ticker=provided_ticker, symbol="ASX:BHP", ex_date="2025-08-15", div_amount=1.5)
        )
        assert result is not None
        assert result.symbol == "BHP.AX"
        # Should NOT have created a new Ticker
        mock_ticker_cls.assert_not_called()

    @patch("app.services.event.yfutils.lookup_peer_yf_static_symbol", return_value=None)
    @patch("app.services.event.yfutils.lookup_index_yf_static_symbol", return_value=None)
    @patch("app.services.event.yf.Ticker")
    def test_returns_none_when_no_past_dividends(self, mock_ticker_cls, mock_lookup_idx, mock_lookup_peer):
        from app.services.event import analyse_dividend_event

        mock_ticker = mock_ticker_cls.return_value
        mock_ticker.info = {
            "quoteType": "EQUITY",
            "regularMarketPrice": 100.0,
            "symbol": "NEW.AX",
            "fullExchangeName": "ASX",
            "longName": "New Company",
            "country": "Australia",
        }
        # 200 days, no dividends
        history = _make_history_df(num_days=200, base_price=100.0, div_days=[])
        mock_ticker.history.return_value = history

        result = asyncio.run(analyse_dividend_event(symbol="ASX:NEW", ex_date="2025-08-15", div_amount=1.0))
        assert result is None

    @patch("app.services.event.yfutils.lookup_peer_yf_static_symbol", return_value="^AXFJ")
    @patch("app.services.event.yfutils.lookup_index_yf_static_symbol", return_value="^AXJO")
    @patch("app.services.event.yf.Ticker")
    def test_fetches_market_and_peer_trends(self, mock_ticker_cls, mock_lookup_idx, mock_lookup_peer):
        from app.services.event import analyse_dividend_event

        main_ticker = MagicMock()
        main_ticker.info = {
            "quoteType": "EQUITY",
            "regularMarketPrice": 120.0,
            "symbol": "CBA.AX",
            "fullExchangeName": "ASX",
            "longName": "Commonwealth Bank",
            "country": "Australia",
            "beta": 1.0,
        }
        history = _make_history_df(num_days=500, base_price=120.0, div_days=[100, 200, 300, 400])
        main_ticker.history.return_value = history

        market_ticker = MagicMock()
        market_ticker.info = {"symbol": "^AXJO"}
        market_ticker.history.return_value = _make_history_df(num_days=62, base_price=7000.0)

        peer_ticker = MagicMock()
        peer_ticker.info = {"symbol": "^AXFJ"}
        peer_ticker.history.return_value = _make_history_df(num_days=62, base_price=6000.0)

        # First call returns main_ticker, second market, third peer
        mock_ticker_cls.side_effect = [main_ticker, market_ticker, peer_ticker]

        result = asyncio.run(analyse_dividend_event(symbol="ASX:CBA", ex_date="2025-08-15", div_amount=2.5))
        assert result is not None
        # market and peer trends should be populated
        assert result.market_trend_60d is not None
        assert result.peer_trend_60d is not None
