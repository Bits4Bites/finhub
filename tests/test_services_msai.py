"""Unit tests for legacy app.services.msai_* modules."""

import asyncio
from unittest.mock import AsyncMock, patch

from app.services import ai_helper


class TestAiAnalyzeTicker:
    """Tests for ai_analyze_ticker function."""

    @patch("app.services.msai_analyze_ticker.cache.get", new_callable=AsyncMock)
    @patch("app.services.msai_analyze_ticker.cache.generate_key", return_value="cache-key")
    @patch("app.services.msai_analyze_ticker.yf.Ticker")
    def test_returns_cached_result(self, mock_ticker_cls, mock_generate_key, mock_cache_get):
        from app.models.ai import AnalysisResult
        from app.services.msai_analyze_ticker import ai_analyze_ticker

        cached_result = AnalysisResult(analysis="Cached analysis")
        mock_cache_get.return_value = cached_result

        result = asyncio.run(ai_analyze_ticker("NASDAQ:AAPL", intent="Growth outlook"))

        assert result is cached_result
        mock_generate_key.assert_called_once_with(
            "ticker-analysis",
            "NASDAQ:AAPL",
            "Growth outlook",
        )
        mock_cache_get.assert_awaited_once_with("cache-key")
        mock_ticker_cls.assert_not_called()

    @patch("app.utils.conv.to_yf_symbol_format", return_value="AAPL")
    @patch("app.services.msai_analyze_ticker.yf.Ticker")
    def test_returns_none_for_unsupported_quote_type(self, mock_ticker_cls, mock_conv):
        from app.services.msai_analyze_ticker import ai_analyze_ticker

        mock_ticker_cls.return_value.info = {"quoteType": "CURRENCY", "country": "US"}
        result = asyncio.run(ai_analyze_ticker("AAPL"))
        assert result is None

    @patch("app.services.msai_analyze_ticker.ai_helper.ai_exec_task", new_callable=AsyncMock)
    @patch("app.utils.conv.to_yf_symbol_format", return_value="AAPL")
    @patch("app.services.msai_analyze_ticker.yf.Ticker")
    def test_returns_error_when_build_prompt_fails(self, mock_ticker_cls, mock_conv, mock_ai_exec):
        from app.services.msai_analyze_ticker import ai_analyze_ticker

        mock_ticker_cls.return_value.info = {
            "quoteType": "EQUITY",
            "country": "US",
            "sector": "Technology",
            "industry": "Consumer Electronics",
            "longName": "Apple Inc.",
            "fullExchangeName": "NASDAQ",
            "exchange": "NMS",
            "symbol": "AAPL",
            "marketCap": 3_000_000_000_000,
        }
        mock_ai_exec.return_value = ai_helper.LLMResponse(is_error=True, error_msg="LLM timeout")

        result = asyncio.run(ai_analyze_ticker("AAPL"))
        assert result is not None
        assert result.llm_error is True
        assert "LLM timeout" in result.llm_error_msg

    @patch("app.services.msai_analyze_ticker.ai_helper.ai_exec_task", new_callable=AsyncMock)
    @patch("app.utils.conv.to_yf_symbol_format", return_value="AAPL")
    @patch("app.services.msai_analyze_ticker.yf.Ticker")
    def test_returns_error_when_exec_fails(self, mock_ticker_cls, mock_conv, mock_ai_exec):
        from app.services.msai_analyze_ticker import ai_analyze_ticker

        mock_ticker_cls.return_value.info = {
            "quoteType": "EQUITY",
            "country": "US",
            "sector": "Technology",
            "industry": "Consumer Electronics",
            "longName": "Apple Inc.",
            "fullExchangeName": "NASDAQ",
            "exchange": "NMS",
            "symbol": "AAPL",
            "marketCap": 3_000_000_000_000,
        }
        mock_ai_exec.side_effect = [
            ai_helper.LLMResponse(completion="Generated prompt"),
            ai_helper.LLMResponse(is_error=True, error_msg="Exec failed"),
        ]

        result = asyncio.run(ai_analyze_ticker("AAPL"))
        assert result is not None
        assert result.llm_error is True
        assert "Exec failed" in result.llm_error_msg

    @patch("app.services.msai_analyze_ticker.ai_helper.ai_exec_task", new_callable=AsyncMock)
    @patch("app.utils.conv.to_yf_symbol_format", return_value="AAPL")
    @patch("app.services.msai_analyze_ticker.yf.Ticker")
    def test_returns_analysis_on_success(self, mock_ticker_cls, mock_conv, mock_ai_exec):
        from app.services.msai_analyze_ticker import ai_analyze_ticker

        mock_ticker_cls.return_value.info = {
            "quoteType": "EQUITY",
            "country": "US",
            "sector": "Technology",
            "industry": "Consumer Electronics",
            "longName": "Apple Inc.",
            "fullExchangeName": "NASDAQ",
            "exchange": "NMS",
            "symbol": "AAPL",
            "marketCap": 3_000_000_000_000,
        }
        mock_ai_exec.side_effect = [
            ai_helper.LLMResponse(completion="Generated prompt"),
            ai_helper.LLMResponse(completion="AAPL looks bullish..."),
        ]

        with (
            patch(
                "app.services.msai_analyze_ticker.cache.get",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "app.services.msai_analyze_ticker.cache.set",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_cache_set,
            patch(
                "app.services.msai_analyze_ticker.cache.generate_key",
                return_value="cache-key",
            ),
        ):
            result = asyncio.run(ai_analyze_ticker("AAPL"))

        assert result is not None
        assert result.llm_error is False
        assert result.analysis == "AAPL looks bullish..."
        mock_cache_set.assert_awaited_once_with("cache-key", result, ttl=72 * 60 * 60)
