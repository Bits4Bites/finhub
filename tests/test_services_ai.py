"""Unit tests for app.services module."""

import asyncio
from unittest.mock import AsyncMock, patch

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

    @patch("app.services.msai_asx_listings._analyze_asx_listings", new_callable=AsyncMock)
    @patch("app.services.msai_asx_listings._get_asx_new_listings", new_callable=AsyncMock)
    def test_calls_analyze_after_get(self, mock_get, mock_analyze):
        from app.services.msai_asx_listings import ai_get_asx_new_listings

        mock_get.return_value = []
        mock_analyze.return_value = []

        asyncio.run(ai_get_asx_new_listings())
        mock_get.assert_called_once()
        mock_analyze.assert_called_once()


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
