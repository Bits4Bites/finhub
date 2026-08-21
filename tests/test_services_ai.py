"""Unit tests for app.services module."""

import asyncio
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from app.models import events_listings as models_events_listings

# ===========================================================================
# Tests for get_symbol_info_raw
# ===========================================================================


class TestGetSymbolInfoRaw:
    """Tests for get_symbol_info_raw function."""

    @patch("app.services.stock.yf.Ticker")
    def test_converts_camel_case_to_snake_case(self, mock_ticker_cls):
        from app.services.stock import get_symbol_info_raw

        mock_ticker_cls.return_value.info = {
            "longName": "Apple Inc.",
            "marketCap": 3_000_000_000_000,
            "regularMarketPrice": 195.0,
        }

        result = get_symbol_info_raw("AAPL")
        assert "long_name" in result
        assert result["long_name"] == "Apple Inc."
        assert "market_cap" in result
        assert "regular_market_price" in result

    @patch("app.services.stock.yf.Ticker")
    def test_handles_empty_info(self, mock_ticker_cls):
        from app.services.stock import get_symbol_info_raw

        mock_ticker_cls.return_value.info = {}
        result = get_symbol_info_raw("INVALID")
        assert result == {}

    @patch("app.services.stock.yf.Ticker")
    def test_preserves_lowercase_keys(self, mock_ticker_cls):
        from app.services.stock import get_symbol_info_raw

        mock_ticker_cls.return_value.info = {"symbol": "AAPL", "exchange": "NMS"}
        result = get_symbol_info_raw("AAPL")
        assert "symbol" in result
        assert "exchange" in result


# ===========================================================================
# Tests for ai_get_asx_new_listings
# ===========================================================================


def _make_listing_event(
    symbol: str = "ASX:XYZ",
    date: str = "2026-06-15",
    *,
    issue_price: float | None = 2.5,
    capital_to_raise: float | None = 5_000_000,
    analysis_status: str = "NotStarted",
) -> models_events_listings.ListingEvent:
    return models_events_listings.ListingEvent(
        symbol=symbol,
        exchange="ASX",
        date=date,
        issue_price=issue_price,
        currency="AUD",
        capital_to_raise=capital_to_raise,
        analysis_status=analysis_status,
    )


class TestAiGetAsxNewListings:
    """Tests for ai_get_asx_new_listings function."""

    @pytest.fixture(autouse=True)
    def mock_cache(self):
        with (
            patch("app.services.msai_asx_listings.cache.get", new_callable=AsyncMock, return_value=None) as mock_get,
            patch("app.services.msai_asx_listings.cache.set", new_callable=AsyncMock, return_value=True) as mock_set,
            patch("app.services.msai_asx_listings._current_asx_date", return_value=date(2026, 6, 15)),
        ):
            self.mock_cache_get = mock_get
            self.mock_cache_set = mock_set
            yield

    @patch("app.services.msai_asx_listings._analyze_asx_listings", new_callable=AsyncMock)
    @patch("app.services.msai_asx_listings._get_asx_new_listings", new_callable=AsyncMock)
    def test_returns_empty_list_when_no_listings(self, mock_get, mock_analyze):
        from app.services.msai_asx_listings import ai_get_asx_new_listings

        mock_get.return_value = []
        mock_analyze.return_value = []

        result = asyncio.run(ai_get_asx_new_listings())
        assert result == []

    @patch("app.services.msai_asx_listings._analyze_asx_listings", new_callable=AsyncMock)
    @patch("app.services.msai_asx_listings._get_asx_new_listings", new_callable=AsyncMock)
    def test_converts_dates_and_timestamps(self, mock_get, mock_analyze):
        from app.services.msai_asx_listings import ai_get_asx_new_listings

        event = _make_listing_event(analysis_status="Completed")
        event.company_name = "XYZ Corp"
        mock_get.return_value = [event]
        mock_analyze.return_value = [event]

        result = asyncio.run(ai_get_asx_new_listings())
        assert len(result) == 1
        assert result[0].date.startswith("2026-06-15")
        assert result[0].timestamp > 0
        self.mock_cache_set.assert_awaited_once()
        assert self.mock_cache_set.await_args.kwargs["ttl"] == 3600

    @patch("app.services.msai_asx_listings._analyze_asx_listings", new_callable=AsyncMock)
    @patch("app.services.msai_asx_listings._get_asx_new_listings", new_callable=AsyncMock)
    def test_calls_analyze_after_get(self, mock_get, mock_analyze):
        from app.services.msai_asx_listings import ai_get_asx_new_listings

        mock_get.return_value = []
        mock_analyze.return_value = []

        asyncio.run(ai_get_asx_new_listings())
        mock_get.assert_called_once()
        mock_analyze.assert_called_once()

    @patch("app.services.msai_asx_listings._analyze_asx_listings", new_callable=AsyncMock)
    @patch("app.services.msai_asx_listings._get_asx_new_listings", new_callable=AsyncMock)
    def test_returns_cached_analysis(self, mock_get, mock_analyze):
        from app.services.msai_asx_listings import ai_get_asx_new_listings

        extracted_event = _make_listing_event()
        cached_events = [
            _make_listing_event(
                date="2026-06-15T00:00:00+10:00",
                analysis_status="Completed",
            )
        ]
        mock_get.return_value = [extracted_event]
        self.mock_cache_get.return_value = cached_events

        result = asyncio.run(ai_get_asx_new_listings())

        assert result == cached_events
        assert result is not cached_events
        mock_analyze.assert_not_awaited()
        self.mock_cache_set.assert_not_awaited()

    @patch("app.services.msai_asx_listings.cache.generate_key", return_value="cache-key")
    @patch("app.services.msai_asx_listings._analyze_asx_listings", new_callable=AsyncMock)
    @patch("app.services.msai_asx_listings._get_asx_new_listings", new_callable=AsyncMock)
    def test_cache_key_uses_sorted_listing_fields(self, mock_get, mock_analyze, mock_generate_key):
        from app.services.msai_asx_listings import ai_get_asx_new_listings

        events = [
            _make_listing_event(
                symbol="ASX:ZZZ",
                date="2026-08-02",
                issue_price=2.5,
                capital_to_raise=10_000_000,
                analysis_status="Completed",
            ),
            _make_listing_event(
                symbol="ASX:AAA",
                date="2026-08-01",
                issue_price=1.25,
                capital_to_raise=5_000_000,
                analysis_status="Completed",
            ),
        ]
        events[0].public_offer_close_date = "2026-07-28"
        events[0].is_underwritten = None
        events[1].is_underwritten = False
        mock_get.return_value = events
        mock_analyze.side_effect = lambda selected: selected

        with (
            patch(
                "app.services.msai_asx_listings._task_cache_identity",
                side_effect=lambda task_id: f"task:{task_id}",
            ),
            patch(
                "app.services.msai_asx_listings._event_input_json",
                side_effect=lambda event: f"event:{event.symbol}",
            ),
        ):
            asyncio.run(ai_get_asx_new_listings())

        mock_generate_key.assert_called_once_with(
            "asx-new-listings-analysis-v3",
            "2026-06-15",
            "task:ASX_LISTTINGS_EXTRACT",
            "task:ASX_LISTTINGS_RESEARCH",
            "task:ASX_LISTTINGS_ANALYZE",
            "task:ASX_LISTTINGS_UNDERWRITTEN_RESEARCH",
            "task:ASX_LISTTINGS_UNDERWRITTEN_ANALYZE",
            "event:ASX:AAA",
            "event:ASX:ZZZ",
        )
        assert [event.symbol for event in mock_analyze.await_args.args[0]] == ["ASX:AAA", "ASX:ZZZ"]
        cached_events = self.mock_cache_set.await_args.args[1]
        assert [event["symbol"] for event in cached_events] == ["ASX:AAA", "ASX:ZZZ"]
        assert self.mock_cache_set.await_args.kwargs["ttl"] == 86400

    @patch("app.services.msai_asx_listings._analyze_asx_listings", new_callable=AsyncMock)
    @patch("app.services.msai_asx_listings._get_asx_new_listings", new_callable=AsyncMock)
    def test_analyzes_only_five_soonest_listings(self, mock_get, mock_analyze):
        from app.services.msai_asx_listings import ai_get_asx_new_listings

        events = [
            _make_listing_event(symbol=f"ASX:A{day}", date=f"2026-09-0{day}", analysis_status="Completed")
            for day in range(6, 0, -1)
        ]
        mock_get.return_value = events
        mock_analyze.side_effect = lambda selected: selected

        result = asyncio.run(ai_get_asx_new_listings())

        assert [event.symbol for event in result] == ["ASX:A1", "ASX:A2", "ASX:A3", "ASX:A4", "ASX:A5"]
        assert [event.symbol for event in mock_analyze.await_args.args[0]] == [
            "ASX:A1",
            "ASX:A2",
            "ASX:A3",
            "ASX:A4",
            "ASX:A5",
        ]

    @patch("app.services.msai_asx_listings._analyze_asx_listings", new_callable=AsyncMock)
    @patch("app.services.msai_asx_listings._get_asx_new_listings", new_callable=AsyncMock)
    def test_filters_by_date_before_applying_listing_cap(self, mock_get, mock_analyze):
        from app.services.msai_asx_listings import ai_get_asx_new_listings

        events = [
            _make_listing_event(symbol="ASX:F5", date="2026-06-20", analysis_status="Completed"),
            _make_listing_event(symbol="ASX:F1", date="2026-06-16", analysis_status="Completed"),
            _make_listing_event(symbol="ASX:PAST", date="2026-06-14", analysis_status="Completed"),
            _make_listing_event(
                symbol="ASX:EF2",
                date="2026-06-15",
                issue_price=None,
                capital_to_raise=None,
                analysis_status="Completed",
            ),
            _make_listing_event(symbol="ASX:F4", date="2026-06-19", analysis_status="Completed"),
            _make_listing_event(symbol="ASX:F3", date="2026-06-18", analysis_status="Completed"),
            _make_listing_event(symbol="ASX:F2", date="2026-06-17", analysis_status="Completed"),
        ]
        mock_get.return_value = events
        mock_analyze.side_effect = lambda selected: selected

        result = asyncio.run(ai_get_asx_new_listings())

        expected_symbols = ["ASX:EF2", "ASX:F1", "ASX:F2", "ASX:F3", "ASX:F4"]
        assert [event.symbol for event in result] == expected_symbols
        assert [event.symbol for event in mock_analyze.await_args.args[0]] == expected_symbols


# ===========================================================================
# Tests for read_file_as_single_string
# ===========================================================================


class TestReadFileAsSingleString:
    """Tests for read_file_as_single_string function."""

    def test_reads_file_content(self, tmp_path):
        from app.services import read_file_as_single_string

        test_file = tmp_path / "test.txt"
        test_file.write_text("line1\nline2\nline3\n", encoding="utf-8")

        result = read_file_as_single_string(str(test_file))
        assert result == "line1\nline2\nline3"

    def test_strips_trailing_whitespace_per_line(self, tmp_path):
        from app.services import read_file_as_single_string

        test_file = tmp_path / "test.txt"
        test_file.write_text("line1   \nline2\t\n", encoding="utf-8")

        result = read_file_as_single_string(str(test_file))
        assert result == "line1\nline2"

    def test_returns_empty_string_for_missing_file(self):
        from app.services import read_file_as_single_string

        result = read_file_as_single_string("/nonexistent/path/file.txt")
        assert result == ""

    def test_returns_empty_string_for_empty_file(self, tmp_path):
        from app.services import read_file_as_single_string

        test_file = tmp_path / "empty.txt"
        test_file.write_text("", encoding="utf-8")

        result = read_file_as_single_string(str(test_file))
        assert result == ""
