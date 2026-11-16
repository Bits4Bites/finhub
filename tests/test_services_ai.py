"""Black-box tests for public functions exposed by app.services."""

import logging
from unittest.mock import patch

import pytest

from app import services
from app.services import stock as services_stock

# ===========================================================================
# Tests for get_symbol_info_raw
# ===========================================================================


class TestGetSymbolInfoRaw:
    """Tests for get_symbol_info_raw function."""

    @patch("app.services.stock.yf.Ticker")
    def test_converts_camel_case_to_snake_case(self, mock_ticker_cls):
        mock_ticker_cls.return_value.info = {
            "longName": "Apple Inc.",
            "marketCap": 3_000_000_000_000,
            "regularMarketPrice": 195.0,
        }

        result = services_stock.get_symbol_info_raw("AAPL")
        assert "long_name" in result
        assert result["long_name"] == "Apple Inc."
        assert "market_cap" in result
        assert "regular_market_price" in result

    @patch("app.services.stock.yf.Ticker")
    def test_handles_empty_info(self, mock_ticker_cls):
        mock_ticker_cls.return_value.info = {}
        result = services_stock.get_symbol_info_raw("INVALID")
        assert result == {}

    @patch("app.services.stock.yf.Ticker")
    def test_preserves_lowercase_keys(self, mock_ticker_cls):
        mock_ticker_cls.return_value.info = {"symbol": "AAPL", "exchange": "NMS"}
        result = services_stock.get_symbol_info_raw("AAPL")
        assert "symbol" in result
        assert "exchange" in result

    @patch("app.services.stock.yf.Ticker")
    def test_provider_metadata_failure_propagates(self, mock_ticker_cls):
        failure = RuntimeError("metadata unavailable")

        class FailingTicker:
            @property
            def info(self):
                raise failure

        mock_ticker_cls.return_value = FailingTicker()

        with pytest.raises(RuntimeError) as error_info:
            services_stock.get_symbol_info_raw("AAPL")

        assert error_info.value is failure


# ===========================================================================
# Tests for read_file_as_single_string
# ===========================================================================


class TestReadFileAsSingleString:
    """Tests for read_file_as_single_string function."""

    def test_accepts_pathlike_and_reads_file_content(self, tmp_path):
        test_file = tmp_path / "test.txt"
        test_file.write_text("line1\nline2\nline3\n", encoding="utf-8")

        result = services.read_file_as_single_string(test_file)
        assert result == "line1\nline2\nline3"

    def test_strips_trailing_whitespace_per_line(self, tmp_path):
        test_file = tmp_path / "test.txt"
        test_file.write_text("line1   \nline2\t\n", encoding="utf-8")

        result = services.read_file_as_single_string(test_file)
        assert result == "line1\nline2"

    def test_returns_empty_string_for_missing_file(self, tmp_path):
        result = services.read_file_as_single_string(tmp_path / "missing.txt")
        assert result == ""

    def test_returns_empty_string_for_empty_file(self, tmp_path):
        test_file = tmp_path / "empty.txt"
        test_file.write_text("", encoding="utf-8")

        result = services.read_file_as_single_string(test_file)
        assert result == ""

    def test_non_missing_read_failure_is_logged_and_not_raised(self, caplog):
        with (
            patch("builtins.open", side_effect=OSError("storage unavailable")),
            caplog.at_level(logging.ERROR),
        ):
            result = services.read_file_as_single_string("prompt.txt")

        assert result == ""
        assert caplog.records
        assert all(record.levelno >= logging.ERROR for record in caplog.records)
