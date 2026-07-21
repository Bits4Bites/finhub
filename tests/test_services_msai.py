"""Unit tests for app.services.msai_* modules."""

import asyncio
from unittest.mock import AsyncMock, patch

from app.models.ai import LLMResponse
from app.models.finhub import HoldingTicker

# ===========================================================================
# Tests for msai_analyze_ticker
# ===========================================================================


class TestAiAnalyzeTicker:
    """Tests for ai_analyze_ticker function."""

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
        mock_ai_exec.return_value = LLMResponse(is_error=True, error_msg="LLM timeout")

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
            LLMResponse(completion="Generated prompt"),
            LLMResponse(is_error=True, error_msg="Exec failed"),
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
            LLMResponse(completion="Generated prompt"),
            LLMResponse(completion="AAPL looks bullish..."),
        ]

        result = asyncio.run(ai_analyze_ticker("AAPL"))
        assert result is not None
        assert result.llm_error is False
        assert result.analysis == "AAPL looks bullish..."


# ===========================================================================
# Tests for msai_build_portfolio
# ===========================================================================


class TestAiBuildPortfolio:
    """Tests for ai_build_portfolio function."""

    @patch("app.services.msai_build_portfolio.ai_helper.ai_exec_task", new_callable=AsyncMock)
    def test_returns_error_when_build_prompt_fails(self, mock_ai_exec):
        from app.services.msai_build_portfolio import ai_build_portfolio

        mock_ai_exec.return_value = LLMResponse(is_error=True, error_msg="Build failed")

        result = asyncio.run(ai_build_portfolio(country="AU"))
        assert result is not None
        assert result.llm_error is True
        assert "Build failed" in result.llm_error_msg

    @patch("app.services.msai_build_portfolio.ai_helper.ai_exec_task", new_callable=AsyncMock)
    def test_returns_error_when_exec_fails(self, mock_ai_exec):
        from app.services.msai_build_portfolio import ai_build_portfolio

        mock_ai_exec.side_effect = [
            LLMResponse(completion="Generated prompt"),
            LLMResponse(is_error=True, error_msg="Exec failed"),
        ]

        result = asyncio.run(ai_build_portfolio(country="US"))
        assert result is not None
        assert result.llm_error is True
        assert "Exec failed" in result.llm_error_msg

    @patch("app.services.msai_build_portfolio.ai_helper.ai_exec_task", new_callable=AsyncMock)
    def test_returns_analysis_on_success(self, mock_ai_exec):
        from app.services.msai_build_portfolio import ai_build_portfolio

        mock_ai_exec.side_effect = [
            LLMResponse(completion="Generated prompt"),
            LLMResponse(completion="Recommended portfolio: ..."),
        ]

        result = asyncio.run(ai_build_portfolio(country="AU"))
        assert result is not None
        assert result.llm_error is False
        assert result.analysis == "Recommended portfolio: ..."

    @patch("app.services.msai_build_portfolio.ai_helper.ai_exec_task", new_callable=AsyncMock)
    def test_includes_existing_positions_in_prompt(self, mock_ai_exec):
        from app.services.msai_build_portfolio import ai_build_portfolio

        mock_ai_exec.side_effect = [
            LLMResponse(completion="Generated prompt"),
            LLMResponse(completion="Portfolio result"),
        ]

        positions = [
            HoldingTicker(ticker="AAPL", num_shares=10, market_price=150.0, tags="growth"),
            HoldingTicker(ticker="MSFT", num_shares=5, market_price=400.0),
        ]

        result = asyncio.run(ai_build_portfolio(country="US", existing_positions=positions))
        assert result is not None
        assert result.analysis == "Portfolio result"

        # Verify the build prompt call included holdings info
        first_call_args = mock_ai_exec.call_args_list[0]
        prompt_input = first_call_args[0][1]  # second positional arg
        assert "AAPL" in prompt_input
        assert "MSFT" in prompt_input
        assert "(growth)" in prompt_input

    @patch("app.services.msai_build_portfolio.ai_helper.ai_exec_task", new_callable=AsyncMock)
    def test_empty_existing_positions_treated_as_none(self, mock_ai_exec):
        from app.services.msai_build_portfolio import ai_build_portfolio

        mock_ai_exec.side_effect = [
            LLMResponse(completion="Generated prompt"),
            LLMResponse(completion="Portfolio result"),
        ]

        result = asyncio.run(ai_build_portfolio(country="AU", existing_positions=[]))
        assert result is not None
        assert result.analysis == "Portfolio result"

        # Verify no holdings info in prompt
        first_call_args = mock_ai_exec.call_args_list[0]
        prompt_input = first_call_args[0][1]
        assert "Current holdings" not in prompt_input


# ===========================================================================
# Tests for msai_review_portfolio
# ===========================================================================


class TestAiSpotlightPortfolio:
    """Tests for ai_spotlight_portfolio function."""

    def test_returns_none_for_empty_portfolio(self):
        from app.services.msai_spotlight_portfolio import ai_spotlight_portfolio

        result = asyncio.run(ai_spotlight_portfolio(portfolio=[], country="AU"))
        assert result is None

    @patch("app.services.msai_spotlight_portfolio.ai_helper.ai_exec_task", new_callable=AsyncMock)
    def test_uses_two_step_prompt_flow(self, mock_ai_exec):
        from app.services.msai_spotlight_portfolio import ai_spotlight_portfolio

        mock_ai_exec.side_effect = [
            LLMResponse(completion="Generated spotlight prompt"),
            LLMResponse(completion="Immediate risks and actions"),
        ]
        portfolio = [HoldingTicker(ticker="AAPL", num_shares=20, avg_price=150.0, market_price=190.0, tags="growth")]

        result = asyncio.run(ai_spotlight_portfolio(portfolio=portfolio, country="US"))

        assert result is not None
        assert result.analysis == "Immediate risks and actions"
        assert mock_ai_exec.call_count == 2
        assert mock_ai_exec.call_args_list[0].args[0] == "SPOTLIGHT_PORTFOLIO_BUILD_PROMPT"
        assert "avg price $150.00, market value $3800.00" in mock_ai_exec.call_args_list[0].args[1]
        assert mock_ai_exec.call_args_list[1].args[0] == "SPOTLIGHT_PORTFOLIO_EXEC"


class TestAiReviewPortfolio:
    """Tests for ai_review_portfolio function."""

    def test_returns_none_for_empty_portfolio(self):
        from app.services.msai_review_portfolio import ai_review_portfolio

        result = asyncio.run(ai_review_portfolio(portfolio=[], country="AU"))
        assert result is None

    @patch("app.services.msai_review_portfolio.ai_helper.ai_exec_task", new_callable=AsyncMock)
    def test_returns_error_when_build_prompt_fails(self, mock_ai_exec):
        from app.services.msai_review_portfolio import ai_review_portfolio

        mock_ai_exec.return_value = LLMResponse(is_error=True, error_msg="Build failed")
        portfolio = [HoldingTicker(ticker="CBA.AX", num_shares=100, market_price=120.0)]

        result = asyncio.run(ai_review_portfolio(portfolio=portfolio, country="AU"))
        assert result is not None
        assert result.llm_error is True
        assert "Build failed" in result.llm_error_msg

    @patch("app.services.msai_review_portfolio.ai_helper.ai_exec_task", new_callable=AsyncMock)
    def test_returns_error_when_exec_fails(self, mock_ai_exec):
        from app.services.msai_review_portfolio import ai_review_portfolio

        mock_ai_exec.side_effect = [
            LLMResponse(completion="Generated prompt"),
            LLMResponse(is_error=True, error_msg="Exec failed"),
        ]
        portfolio = [HoldingTicker(ticker="CBA.AX", num_shares=100, market_price=120.0)]

        result = asyncio.run(ai_review_portfolio(portfolio=portfolio, country="AU"))
        assert result is not None
        assert result.llm_error is True
        assert "Exec failed" in result.llm_error_msg

    @patch("app.services.msai_review_portfolio.ai_helper.ai_exec_task", new_callable=AsyncMock)
    def test_returns_analysis_on_success(self, mock_ai_exec):
        from app.services.msai_review_portfolio import ai_review_portfolio

        mock_ai_exec.side_effect = [
            LLMResponse(completion="Generated prompt"),
            LLMResponse(completion="Portfolio review: well diversified..."),
        ]
        portfolio = [
            HoldingTicker(ticker="CBA.AX", num_shares=100, market_price=120.0),
            HoldingTicker(ticker="BHP.AX", num_shares=50, market_price=45.0),
        ]

        result = asyncio.run(ai_review_portfolio(portfolio=portfolio, country="AU"))
        assert result is not None
        assert result.llm_error is False
        assert result.analysis == "Portfolio review: well diversified..."

    @patch("app.services.msai_review_portfolio.ai_helper.ai_exec_task", new_callable=AsyncMock)
    def test_includes_portfolio_positions_in_prompt(self, mock_ai_exec):
        from app.services.msai_review_portfolio import ai_review_portfolio

        mock_ai_exec.side_effect = [
            LLMResponse(completion="Generated prompt"),
            LLMResponse(completion="Review result"),
        ]
        portfolio = [HoldingTicker(ticker="AAPL", num_shares=20, market_price=190.0, tags="growth")]

        asyncio.run(ai_review_portfolio(portfolio=portfolio, country="US"))

        first_call_args = mock_ai_exec.call_args_list[0]
        prompt_input = first_call_args[0][1]
        assert "AAPL" in prompt_input
        assert "20" in prompt_input
        assert "(growth)" in prompt_input


# ===========================================================================
# Tests for msai_analyze_div_event
# ===========================================================================


class TestAiAnalyzeDivEvent:
    """Tests for ai_analyze_div_event function."""

    @patch("app.services.msai_analyze_div_event.services_event.analyse_dividend_event", new_callable=AsyncMock)
    @patch("app.utils.conv.to_yf_symbol_format", return_value="CBA.AX")
    @patch("app.services.msai_analyze_div_event.yf.Ticker")
    def test_returns_none_when_pre_analysis_fails(self, mock_ticker_cls, mock_conv, mock_analyse):
        from app.services.msai_analyze_div_event import ai_analyze_div_event

        mock_ticker_cls.return_value.info = {"country": "Australia"}
        mock_analyse.return_value = None

        result = asyncio.run(ai_analyze_div_event(symbol="ASX:CBA", ex_date="2025-08-15", div_amount=2.50))
        assert result is None

    @patch("app.services.msai_analyze_div_event.ai_helper.ai_exec_task", new_callable=AsyncMock)
    @patch("app.services.msai_analyze_div_event.services_event.analyse_dividend_event", new_callable=AsyncMock)
    @patch("app.utils.conv.to_yf_symbol_format", return_value="CBA.AX")
    @patch("app.services.msai_analyze_div_event.yf.Ticker")
    def test_returns_error_when_build_prompt_fails(self, mock_ticker_cls, mock_conv, mock_analyse, mock_ai_exec):
        from app.models.event import DividendEventAnalysis
        from app.services.msai_analyze_div_event import ai_analyze_div_event

        mock_ticker_cls.return_value.info = {
            "country": "Australia",
            "quoteType": "EQUITY",
            "sector": "Financials",
            "industry": "Banks",
            "longName": "Commonwealth Bank",
            "fullExchangeName": "ASX",
            "exchange": "ASX",
            "symbol": "CBA.AX",
            "marketCap": 200_000_000_000,
        }
        mock_analyse.return_value = DividendEventAnalysis(symbol="CBA.AX", price=120.0)
        mock_ai_exec.return_value = LLMResponse(is_error=True, error_msg="Build timeout")

        result = asyncio.run(ai_analyze_div_event(symbol="ASX:CBA", ex_date="2025-08-15", div_amount=2.50))
        assert result is not None
        assert result.llm_error is True
        assert "Build timeout" in result.llm_error_msg

    @patch("app.services.msai_analyze_div_event.ai_helper.ai_exec_task", new_callable=AsyncMock)
    @patch("app.services.msai_analyze_div_event.services_event.analyse_dividend_event", new_callable=AsyncMock)
    @patch("app.utils.conv.to_yf_symbol_format", return_value="CBA.AX")
    @patch("app.services.msai_analyze_div_event.yf.Ticker")
    def test_returns_error_when_exec_fails(self, mock_ticker_cls, mock_conv, mock_analyse, mock_ai_exec):
        from app.models.event import DividendEventAnalysis
        from app.services.msai_analyze_div_event import ai_analyze_div_event

        mock_ticker_cls.return_value.info = {
            "country": "Australia",
            "quoteType": "EQUITY",
            "sector": "Financials",
            "industry": "Banks",
            "longName": "Commonwealth Bank",
            "fullExchangeName": "ASX",
            "exchange": "ASX",
            "symbol": "CBA.AX",
            "marketCap": 200_000_000_000,
        }
        mock_analyse.return_value = DividendEventAnalysis(symbol="CBA.AX", price=120.0)
        mock_ai_exec.side_effect = [
            LLMResponse(completion="Generated prompt"),
            LLMResponse(is_error=True, error_msg="Exec timeout"),
        ]

        result = asyncio.run(ai_analyze_div_event(symbol="ASX:CBA", ex_date="2025-08-15", div_amount=2.50))
        assert result is not None
        assert result.llm_error is True
        assert "Exec timeout" in result.llm_error_msg

    @patch("app.services.msai_analyze_div_event.ai_helper.ai_exec_task", new_callable=AsyncMock)
    @patch("app.services.msai_analyze_div_event.services_event.analyse_dividend_event", new_callable=AsyncMock)
    @patch("app.utils.conv.to_yf_symbol_format", return_value="CBA.AX")
    @patch("app.services.msai_analyze_div_event.yf.Ticker")
    def test_returns_full_result_on_success(self, mock_ticker_cls, mock_conv, mock_analyse, mock_ai_exec):
        import json

        from app.models.event import DividendEventAnalysis
        from app.services.msai_analyze_div_event import ai_analyze_div_event

        mock_ticker_cls.return_value.info = {
            "country": "Australia",
            "quoteType": "EQUITY",
            "sector": "Financials",
            "industry": "Banks",
            "longName": "Commonwealth Bank",
            "fullExchangeName": "ASX",
            "exchange": "ASX",
            "symbol": "CBA.AX",
            "marketCap": 200_000_000_000,
        }
        mock_analyse.return_value = DividendEventAnalysis(symbol="CBA.AX", price=120.0)

        llm_json = json.dumps(
            {
                "search_summary": "Positive sentiment overall",
                "strategy": "Dividend Capture",
                "reasoning": "Strong recovery history",
                "sent_score": 0.65,
                "recov_prob_adj": 0.80,
                "eff_div": 0.035,
                "recovery_days": "3-7",
                "est_drop_price": "117.50-118.50",
                "est_recovery_price": "119.80-120.50",
                "expected_pl": 1.25,
                "confidence": 72,
                "risk": 35,
                "risk_factors": ["earnings approaching"],
            }
        )

        mock_ai_exec.side_effect = [
            LLMResponse(completion="Generated prompt"),
            LLMResponse(completion=llm_json),
        ]

        result = asyncio.run(ai_analyze_div_event(symbol="ASX:CBA", ex_date="2025-08-15", div_amount=2.50))
        assert result is not None
        assert result.llm_error is False
        assert result.strategy == "Dividend Capture"
        assert result.search_summary == "Positive sentiment overall"
        assert result.reasoning == "Strong recovery history"
        assert result.sentiment_score == 0.65
        assert result.recovery_probability_adj == 0.80
        assert result.recovery_days_adj == "3-7"
        assert result.confidence_level == 72
        assert result.risk_level == 35
