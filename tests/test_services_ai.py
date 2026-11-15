"""Unit tests for app.services module."""

import asyncio
import logging
from datetime import datetime, time, timedelta
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest

from app import services
from app.models import events_listings as models_events_listings
from app.services import msai_asx_listings
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
        class FailingTicker:
            @property
            def info(self):
                raise RuntimeError("metadata unavailable")

        mock_ticker_cls.return_value = FailingTicker()

        with pytest.raises(RuntimeError, match="metadata unavailable"):
            services_stock.get_symbol_info_raw("AAPL")


# ===========================================================================
# Tests for ai_get_asx_new_listings
# ===========================================================================


def _asx_listing_html() -> str:
    return """
    <div class="multi-column-height">
      Example issuer. Listing date and offer details are available.
    </div>
    """


def _asx_candidate(
    *,
    listing_date,
    issue_price: float | None = 2.5,
) -> dict[str, object]:
    return {
        "symbol": "XYZ",
        "company_name": "XYZ Corp",
        "listing_date": listing_date.isoformat(),
        "issue_price": issue_price,
        "issue_price_upper": None,
        "issue_type": "Ordinary shares",
        "capital_to_raise": 5_000_000,
        "is_underwritten": False,
        "underwriters": [],
        "lead_managers": [],
        "principal_activities": "Technology services",
        "sector": "TECHNOLOGY",
        "public_offer_close_date": None,
    }


def _make_cached_listing_event(
    listing_date,
    *,
    issue_price: float = 2.5,
) -> models_events_listings.ListingEvent:
    listing_at = datetime.combine(
        listing_date,
        time.min,
        tzinfo=ZoneInfo("Australia/Sydney"),
    )
    return models_events_listings.ListingEvent(
        symbol="ASX:XYZ",
        exchange="ASX",
        company_name="XYZ Corp",
        timestamp=int(listing_at.timestamp()),
        timestamp_str=listing_at.isoformat(sep=" "),
        issue_price=issue_price,
        currency="AUD",
        capital_to_raise=5_000_000,
        analysis_status="Completed",
    )


class TestAiGetAsxNewListings:
    """Public-contract tests for ai_get_asx_new_listings."""

    def test_returns_empty_list_when_page_has_no_listing_blocks(self):
        with (
            patch(
                "app.services.msai_asx_listings.services_crawler_core.fetch_webpage_content",
                new_callable=AsyncMock,
                return_value="<html></html>",
            ),
            patch(
                "app.services.msai_asx_listings.cache.get",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "app.services.msai_asx_listings.cache.set",
                new_callable=AsyncMock,
                return_value=True,
            ),
        ):
            result = asyncio.run(msai_asx_listings.ai_get_asx_new_listings())

        assert result == []

    def test_returns_validated_cached_analysis_without_invoking_ai(self):
        listing_date = datetime.now(ZoneInfo("Australia/Sydney")).date() + timedelta(days=2)
        extracted = {"listings": [_asx_candidate(listing_date=listing_date)]}
        cached_event = _make_cached_listing_event(listing_date)
        cache_values = iter([extracted, [cached_event]])

        with (
            patch(
                "app.services.msai_asx_listings.services_crawler_core.fetch_webpage_content",
                new_callable=AsyncMock,
                return_value=_asx_listing_html(),
            ),
            patch(
                "app.services.msai_asx_listings.cache.get",
                new_callable=AsyncMock,
                side_effect=lambda _key: next(cache_values),
            ),
            patch(
                "app.services.msai_asx_listings.ai_helper.ai_exec_task",
                new_callable=AsyncMock,
            ) as ai_exec,
        ):
            result = asyncio.run(msai_asx_listings.ai_get_asx_new_listings())

        assert result == [cached_event]
        assert result[0] is not cached_event
        ai_exec.assert_not_awaited()

    def test_changed_listing_terms_do_not_return_stale_cached_analysis(self):
        listing_date = datetime.now(ZoneInfo("Australia/Sydney")).date() + timedelta(days=5)
        issue_price = 1.25
        cache_get_count = 0
        cached_analyses = {}

        async def cache_get(key):
            nonlocal cache_get_count
            cache_get_count += 1
            if cache_get_count % 2:
                return {
                    "listings": [
                        _asx_candidate(
                            listing_date=listing_date,
                            issue_price=issue_price,
                        )
                    ]
                }
            if not cached_analyses:
                cached_analyses[key] = [
                    _make_cached_listing_event(
                        listing_date,
                        issue_price=issue_price,
                    )
                ]
            return cached_analyses.get(key)

        with (
            patch(
                "app.services.msai_asx_listings.services_crawler_core.fetch_webpage_content",
                new_callable=AsyncMock,
                return_value=_asx_listing_html(),
            ),
            patch(
                "app.services.msai_asx_listings.cache.get",
                side_effect=cache_get,
            ),
            patch(
                "app.services.msai_asx_listings.cache.set",
                new_callable=AsyncMock,
                return_value=True,
            ) as cache_set,
            patch(
                "app.services.msai_asx_listings.config.settings_llm_task.tokenomics_mode",
                "Economy",
            ),
            patch(
                "app.services.msai_asx_listings.ai_helper.ai_exec_task",
                new_callable=AsyncMock,
            ) as ai_exec,
        ):
            first = asyncio.run(msai_asx_listings.ai_get_asx_new_listings())
            second = asyncio.run(msai_asx_listings.ai_get_asx_new_listings())
            issue_price = 2.5
            changed = asyncio.run(msai_asx_listings.ai_get_asx_new_listings())

        assert first == second
        assert first[0].issue_price == 1.25
        assert first[0].analysis_status == "Completed"
        assert changed[0].issue_price == 2.5
        assert changed[0].analysis_status == "Skipped"
        assert changed != first
        ai_exec.assert_not_awaited()
        cache_set.assert_not_awaited()


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

    def test_returns_empty_string_for_missing_file(self):
        result = services.read_file_as_single_string("/nonexistent/path/file.txt")
        assert result == ""

    def test_returns_empty_string_for_empty_file(self, tmp_path):
        test_file = tmp_path / "empty.txt"
        test_file.write_text("", encoding="utf-8")

        result = services.read_file_as_single_string(test_file)
        assert result == ""

    def test_logs_non_missing_read_failure(self, caplog):
        with (
            patch("builtins.open", side_effect=OSError("storage unavailable")),
            caplog.at_level(logging.ERROR),
        ):
            result = services.read_file_as_single_string("prompt.txt")

        assert result == ""
        assert "An unexpected error occurred while reading file 'prompt.txt'" in caplog.text
        assert "storage unavailable" in caplog.text
