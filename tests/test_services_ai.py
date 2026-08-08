"""Unit tests for app.services module."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

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


class TestAiGetAsxNewListings:
    """Tests for ai_get_asx_new_listings function."""

    @pytest.fixture(autouse=True)
    def mock_cache(self):
        with (
            patch("app.services.msai_asx_listings.cache.get", new_callable=AsyncMock, return_value=None) as mock_get,
            patch("app.services.msai_asx_listings.cache.set", new_callable=AsyncMock, return_value=True) as mock_set,
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
        from app.models.event import ListingEvent
        from app.services.msai_asx_listings import ai_get_asx_new_listings

        event = ListingEvent(
            symbol="ASX:XYZ",
            company_name="XYZ Corp",
            date="2026-06-15",
            price=2.5,
        )
        mock_get.return_value = [event]
        mock_analyze.return_value = [event]

        result = asyncio.run(ai_get_asx_new_listings())
        assert len(result) == 1
        assert result[0].date.startswith("2026-06-15")
        assert result[0].timestamp > 0
        self.mock_cache_set.assert_awaited_once()
        assert self.mock_cache_set.await_args.kwargs["ttl"] == 259200

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
        from app.models.event import ListingEvent
        from app.services.msai_asx_listings import ai_get_asx_new_listings

        extracted_event = ListingEvent(symbol="ASX:XYZ", date="2026-06-15", price=2.5)
        cached_events = [ListingEvent(symbol="ASX:XYZ", date="2026-06-15T00:00:00+10:00", price=2.5)]
        mock_get.return_value = [extracted_event]
        self.mock_cache_get.return_value = cached_events

        result = asyncio.run(ai_get_asx_new_listings())

        assert result is cached_events
        mock_analyze.assert_not_awaited()
        self.mock_cache_set.assert_not_awaited()

    @patch("app.services.msai_asx_listings.cache.generate_key", return_value="cache-key")
    @patch("app.services.msai_asx_listings._analyze_asx_listings", new_callable=AsyncMock)
    @patch("app.services.msai_asx_listings._get_asx_new_listings", new_callable=AsyncMock)
    def test_cache_key_uses_sorted_listing_fields(self, mock_get, mock_analyze, mock_generate_key):
        from app.models.event import ListingEvent
        from app.services.msai_asx_listings import ai_get_asx_new_listings

        events = [
            ListingEvent(
                symbol="ASX:ZZZ",
                date="2026-08-02",
                price=2.5,
                public_offer_close_date="2026-07-28",
            ),
            ListingEvent(
                symbol="ASX:AAA",
                date="2026-08-01",
                price=1.25,
                public_offer_close_date=None,
            ),
        ]
        mock_get.return_value = events
        mock_analyze.return_value = events

        asyncio.run(ai_get_asx_new_listings())

        mock_generate_key.assert_called_once_with(
            "asx-new-listings-analysis",
            "ASX:AAA",
            "2026-08-01",
            "1.25",
            "",
            "ASX:ZZZ",
            "2026-08-02",
            "2.5",
            "2026-07-28",
        )
        assert [event.symbol for event in mock_analyze.await_args.args[0]] == ["ASX:AAA", "ASX:ZZZ"]
        self.mock_cache_set.assert_awaited_once_with("cache-key", events, ttl=259200)


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
