"""Unit tests for app.services.msai_* modules."""

import asyncio
from unittest.mock import AsyncMock, patch

from app.models import portfolio as models_portfolio
from app.services import ai_helper

# ===========================================================================
# Tests for msai_analyze_ticker
# ===========================================================================


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


# ===========================================================================
# Tests for msai_build_portfolio
# ===========================================================================


class TestAiBuildPortfolio:
    """Tests for ai_build_portfolio function."""

    @patch("app.services.msai_build_portfolio.cache.get", new_callable=AsyncMock)
    @patch("app.services.msai_build_portfolio.cache.generate_key", return_value="cache-key")
    @patch("app.services.msai_build_portfolio.ai_helper.ai_exec_task", new_callable=AsyncMock)
    def test_returns_cached_result(self, mock_ai_exec, mock_generate_key, mock_cache_get):
        from app.models.ai import AnalyzePortfolioResult
        from app.services.msai_build_portfolio import ai_build_portfolio

        positions = [
            models_portfolio.PortfolioHolding(
                ticker="MSFT",
                num_shares=5,
                avg_price=300,
                market_price=450,
                target_allocation=0.4,
                tags="technology",
            ),
            models_portfolio.PortfolioHolding(
                ticker="AAPL",
                num_shares=10,
                avg_price=125,
                market_price=200,
                target_allocation=0.6,
                tags="growth",
            ),
        ]
        cached_result = AnalyzePortfolioResult(analysis="Cached portfolio")
        mock_cache_get.return_value = cached_result

        result = asyncio.run(
            ai_build_portfolio(
                existing_positions=positions,
                country="US",
                investor_theme="Growth focused",
            )
        )

        assert result is cached_result
        mock_generate_key.assert_called_once_with(
            "build-portfolio-analysis",
            "US",
            "Growth focused",
            "AAPL",
            "10.0",
            "125.0",
            "0.6",
            "MSFT",
            "5.0",
            "300.0",
            "0.4",
        )
        mock_cache_get.assert_awaited_once_with("cache-key")
        mock_ai_exec.assert_not_awaited()
        assert [position.ticker for position in positions] == ["MSFT", "AAPL"]

    @patch("app.services.msai_build_portfolio.ai_helper.ai_exec_task", new_callable=AsyncMock)
    def test_returns_error_when_build_prompt_fails(self, mock_ai_exec):
        from app.services.msai_build_portfolio import ai_build_portfolio

        mock_ai_exec.return_value = ai_helper.LLMResponse(is_error=True, error_msg="Build failed")

        result = asyncio.run(ai_build_portfolio(country="AU"))
        assert result is not None
        assert result.llm_error is True
        assert "Build failed" in result.llm_error_msg

    @patch("app.services.msai_build_portfolio.ai_helper.ai_exec_task", new_callable=AsyncMock)
    def test_returns_error_when_exec_fails(self, mock_ai_exec):
        from app.services.msai_build_portfolio import ai_build_portfolio

        mock_ai_exec.side_effect = [
            ai_helper.LLMResponse(completion="Generated prompt"),
            ai_helper.LLMResponse(is_error=True, error_msg="Exec failed"),
        ]

        result = asyncio.run(ai_build_portfolio(country="US"))
        assert result is not None
        assert result.llm_error is True
        assert "Exec failed" in result.llm_error_msg

    @patch("app.services.msai_build_portfolio.ai_helper.ai_exec_task", new_callable=AsyncMock)
    def test_returns_analysis_on_success(self, mock_ai_exec):
        from app.services.msai_build_portfolio import ai_build_portfolio

        mock_ai_exec.side_effect = [
            ai_helper.LLMResponse(completion="Generated prompt"),
            ai_helper.LLMResponse(completion="Recommended portfolio: ..."),
        ]

        with (
            patch(
                "app.services.msai_build_portfolio.cache.get",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "app.services.msai_build_portfolio.cache.set",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_cache_set,
            patch(
                "app.services.msai_build_portfolio.cache.generate_key",
                return_value="cache-key",
            ),
        ):
            result = asyncio.run(ai_build_portfolio(country="AU"))

        assert result is not None
        assert result.llm_error is False
        assert result.analysis == "Recommended portfolio: ..."
        mock_cache_set.assert_awaited_once_with("cache-key", result, ttl=72 * 60 * 60)

    @patch("app.services.msai_build_portfolio.ai_helper.ai_exec_task", new_callable=AsyncMock)
    def test_includes_existing_positions_in_prompt(self, mock_ai_exec):
        from app.services.msai_build_portfolio import ai_build_portfolio

        mock_ai_exec.side_effect = [
            ai_helper.LLMResponse(completion="Generated prompt"),
            ai_helper.LLMResponse(completion="Portfolio result"),
        ]

        positions = [
            models_portfolio.PortfolioHolding(ticker="AAPL", num_shares=10, market_price=150.0, tags="growth"),
            models_portfolio.PortfolioHolding(ticker="MSFT", num_shares=5, market_price=400.0),
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
            ai_helper.LLMResponse(completion="Generated prompt"),
            ai_helper.LLMResponse(completion="Portfolio result"),
        ]

        result = asyncio.run(ai_build_portfolio(country="AU", existing_positions=[]))
        assert result is not None
        assert result.analysis == "Portfolio result"

        # Verify no holdings info in prompt
        first_call_args = mock_ai_exec.call_args_list[0]
        prompt_input = first_call_args[0][1]
        assert "Current holdings" not in prompt_input


class TestAiReviewPortfolio:
    """Tests for ai_review_portfolio function."""

    def setup_method(self):
        from app.utils import cache

        asyncio.run(cache.clear())

    @patch("app.services.msai_review_portfolio.cache.get", new_callable=AsyncMock)
    @patch("app.services.msai_review_portfolio.cache.generate_key", return_value="cache-key")
    @patch("app.services.msai_review_portfolio.ai_helper.ai_exec_task", new_callable=AsyncMock)
    def test_returns_cached_result(self, mock_ai_exec, mock_generate_key, mock_cache_get):
        from app.models.ai import AnalyzePortfolioResult
        from app.services.msai_review_portfolio import ai_review_portfolio

        portfolio = [
            models_portfolio.PortfolioHolding(
                ticker="MSFT",
                num_shares=5,
                avg_price=300,
                market_price=450,
                target_allocation=0.4,
                tags="technology",
            ),
            models_portfolio.PortfolioHolding(
                ticker="AAPL",
                num_shares=10,
                avg_price=125,
                market_price=200,
                target_allocation=0.6,
                tags="growth",
            ),
        ]
        cached_result = AnalyzePortfolioResult(analysis="Cached review")
        mock_cache_get.return_value = cached_result

        result = asyncio.run(
            ai_review_portfolio(
                portfolio=portfolio,
                country="US",
                investor_theme="Growth focused",
                rebalance_plan=True,
            )
        )

        assert result is cached_result
        mock_generate_key.assert_called_once_with(
            "review-portfolio-analysis",
            "US",
            "Growth focused",
            "True",
            "AAPL",
            "10.0",
            "125.0",
            "0.6",
            "MSFT",
            "5.0",
            "300.0",
            "0.4",
        )
        mock_cache_get.assert_awaited_once_with("cache-key")
        mock_ai_exec.assert_not_awaited()
        assert [position.ticker for position in portfolio] == ["MSFT", "AAPL"]

    def test_returns_none_for_empty_portfolio(self):
        from app.services.msai_review_portfolio import ai_review_portfolio

        result = asyncio.run(ai_review_portfolio(portfolio=[], country="AU"))
        assert result is None

    @patch("app.services.msai_review_portfolio.ai_helper.ai_exec_task", new_callable=AsyncMock)
    def test_returns_error_when_build_prompt_fails(self, mock_ai_exec):
        from app.services.msai_review_portfolio import ai_review_portfolio

        mock_ai_exec.return_value = ai_helper.LLMResponse(is_error=True, error_msg="Build failed")
        portfolio = [models_portfolio.PortfolioHolding(ticker="CBA.AX", num_shares=100, market_price=120.0)]

        result = asyncio.run(ai_review_portfolio(portfolio=portfolio, country="AU"))
        assert result is not None
        assert result.llm_error is True
        assert "Build failed" in result.llm_error_msg

    @patch("app.services.msai_review_portfolio.ai_helper.ai_exec_task", new_callable=AsyncMock)
    def test_returns_error_when_exec_fails(self, mock_ai_exec):
        from app.services.msai_review_portfolio import ai_review_portfolio

        mock_ai_exec.side_effect = [
            ai_helper.LLMResponse(completion="Generated prompt"),
            ai_helper.LLMResponse(is_error=True, error_msg="Exec failed"),
        ]
        portfolio = [models_portfolio.PortfolioHolding(ticker="CBA.AX", num_shares=100, market_price=120.0)]

        result = asyncio.run(ai_review_portfolio(portfolio=portfolio, country="AU"))
        assert result is not None
        assert result.llm_error is True
        assert "Exec failed" in result.llm_error_msg

    @patch("app.services.msai_review_portfolio.ai_helper.ai_exec_task", new_callable=AsyncMock)
    def test_returns_analysis_on_success(self, mock_ai_exec):
        from app.services.msai_review_portfolio import ai_review_portfolio

        mock_ai_exec.side_effect = [
            ai_helper.LLMResponse(completion="Generated prompt"),
            ai_helper.LLMResponse(completion="Portfolio review: well diversified...\n\nREBALANCE_NEEDED: NO"),
        ]
        portfolio = [
            models_portfolio.PortfolioHolding(ticker="CBA.AX", num_shares=100, market_price=120.0),
            models_portfolio.PortfolioHolding(ticker="BHP.AX", num_shares=50, market_price=45.0),
        ]

        with (
            patch(
                "app.services.msai_review_portfolio.cache.get",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "app.services.msai_review_portfolio.cache.set",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_cache_set,
            patch(
                "app.services.msai_review_portfolio.cache.generate_key",
                return_value="cache-key",
            ),
        ):
            result = asyncio.run(ai_review_portfolio(portfolio=portfolio, country="AU"))

        assert result is not None
        assert result.llm_error is False
        assert result.analysis == "Portfolio review: well diversified..."
        assert result.rebalance_plan == ""
        assert mock_ai_exec.call_count == 2
        mock_cache_set.assert_awaited_once_with("cache-key", result, ttl=72 * 60 * 60)

    @patch("app.services.msai_review_portfolio.ai_helper.ai_exec_task", new_callable=AsyncMock)
    def test_generates_rebalance_plan_with_low_cost_preparation_and_premium_execution(self, mock_ai_exec):
        from app.services.msai_review_portfolio import ai_review_portfolio

        mock_ai_exec.side_effect = [
            ai_helper.LLMResponse(completion="Generated review prompt"),
            ai_helper.LLMResponse(completion="Premium portfolio review\n\nREBALANCE_NEEDED: YES"),
            ai_helper.LLMResponse(completion="Low-cost review summary"),
            ai_helper.LLMResponse(completion="Generated rebalance prompt"),
            ai_helper.LLMResponse(completion="Premium rebalance plan"),
        ]
        portfolio = [
            models_portfolio.PortfolioHolding(
                ticker="CBA.AX",
                num_shares=100,
                avg_price=100.0,
                market_price=120.0,
                tags="core",
            )
        ]

        result = asyncio.run(
            ai_review_portfolio(
                portfolio=portfolio,
                country="AU",
                rebalance_plan=True,
            )
        )

        assert result is not None
        assert result.llm_error is False
        assert result.analysis == "Premium portfolio review"
        assert result.rebalance_plan == "Premium rebalance plan"
        assert [call.args[0] for call in mock_ai_exec.call_args_list] == [
            "REVIEW_PORTFOLIO_BUILD_PROMPT",
            "REVIEW_PORTFOLIO_EXEC",
            "REVIEW_PORTFOLIO_SUMMARIZE",
            "REVIEW_PORTFOLIO_REBALANCE_BUILD_PROMPT",
            "REVIEW_PORTFOLIO_REBALANCE_EXEC",
        ]
        assert "Premium portfolio review" in mock_ai_exec.call_args_list[2].args[1]
        assert "REBALANCE_NEEDED" not in mock_ai_exec.call_args_list[2].args[1]
        assert "Premium portfolio review" not in mock_ai_exec.call_args_list[3].args[1]
        assert "Low-cost review summary" in mock_ai_exec.call_args_list[3].args[1]
        assert mock_ai_exec.call_args_list[4].args[1] == "Generated rebalance prompt"

    @patch("app.services.msai_review_portfolio.ai_helper.ai_exec_task", new_callable=AsyncMock)
    def test_skips_rebalance_pipeline_when_major_rebalance_is_not_needed(self, mock_ai_exec):
        from app.services.msai_review_portfolio import ai_review_portfolio

        portfolio_review = "Portfolio is healthy. Continue monitoring.\n\nREBALANCE_NEEDED: NO"
        mock_ai_exec.side_effect = [
            ai_helper.LLMResponse(completion="Generated review prompt"),
            ai_helper.LLMResponse(completion=portfolio_review),
        ]
        portfolio = [models_portfolio.PortfolioHolding(ticker="CBA.AX", num_shares=100, market_price=120.0)]

        result = asyncio.run(
            ai_review_portfolio(
                portfolio=portfolio,
                country="AU",
                rebalance_plan=True,
            )
        )

        assert result is not None
        assert result.llm_error is False
        assert result.analysis == "Portfolio is healthy. Continue monitoring."
        assert result.rebalance_plan == "No rebalance needed"
        assert mock_ai_exec.call_count == 2
        assert "REBALANCE_NEEDED: YES" in mock_ai_exec.call_args_list[0].args[1]
        assert "REBALANCE_NEEDED: NO" in mock_ai_exec.call_args_list[0].args[1]

    @patch("app.services.msai_review_portfolio.ai_helper.ai_exec_task", new_callable=AsyncMock)
    def test_accepts_markdown_wrapped_rebalance_flag(self, mock_ai_exec):
        from app.services.msai_review_portfolio import ai_review_portfolio

        mock_ai_exec.side_effect = [
            ai_helper.LLMResponse(completion="Generated review prompt"),
            ai_helper.LLMResponse(completion="Portfolio is healthy.\n\n**REBALANCE_NEEDED: NO**"),
        ]
        portfolio = [models_portfolio.PortfolioHolding(ticker="CBA.AX", num_shares=100, market_price=120.0)]

        result = asyncio.run(
            ai_review_portfolio(
                portfolio=portfolio,
                country="AU",
                rebalance_plan=True,
            )
        )

        assert result is not None
        assert result.analysis == "Portfolio is healthy."
        assert result.rebalance_plan == "No rebalance needed"
        assert result.llm_error is False
        assert mock_ai_exec.call_count == 2

    @patch("app.services.msai_review_portfolio.ai_helper.ai_exec_task", new_callable=AsyncMock)
    def test_returns_error_when_rebalance_flag_is_missing(self, mock_ai_exec):
        from app.services.msai_review_portfolio import ai_review_portfolio

        mock_ai_exec.side_effect = [
            ai_helper.LLMResponse(completion="Generated review prompt"),
            ai_helper.LLMResponse(completion="Premium portfolio review without the required flag"),
        ]
        portfolio = [models_portfolio.PortfolioHolding(ticker="CBA.AX", num_shares=100, market_price=120.0)]

        result = asyncio.run(
            ai_review_portfolio(
                portfolio=portfolio,
                country="AU",
                rebalance_plan=True,
            )
        )

        assert result is not None
        assert result.analysis == "Premium portfolio review without the required flag"
        assert result.rebalance_plan == ""
        assert result.llm_error is True
        assert "REBALANCE_NEEDED" in result.llm_error_msg
        assert mock_ai_exec.call_count == 2

    @patch("app.services.msai_review_portfolio.ai_helper.ai_exec_task", new_callable=AsyncMock)
    def test_preserves_review_when_rebalance_summary_fails(self, mock_ai_exec):
        from app.services.msai_review_portfolio import ai_review_portfolio

        mock_ai_exec.side_effect = [
            ai_helper.LLMResponse(completion="Generated review prompt"),
            ai_helper.LLMResponse(completion="Premium portfolio review\n\nREBALANCE_NEEDED: YES"),
            ai_helper.LLMResponse(is_error=True, error_msg="Summary failed"),
        ]
        portfolio = [models_portfolio.PortfolioHolding(ticker="CBA.AX", num_shares=100, market_price=120.0)]

        result = asyncio.run(
            ai_review_portfolio(
                portfolio=portfolio,
                country="AU",
                rebalance_plan=True,
            )
        )

        assert result is not None
        assert result.analysis == "Premium portfolio review"
        assert result.rebalance_plan == ""
        assert result.llm_error is True
        assert result.llm_error_msg == "Summary failed"

    @patch("app.services.msai_review_portfolio.ai_helper.ai_exec_task", new_callable=AsyncMock)
    def test_preserves_review_when_rebalance_prompt_build_fails(self, mock_ai_exec):
        from app.services.msai_review_portfolio import ai_review_portfolio

        mock_ai_exec.side_effect = [
            ai_helper.LLMResponse(completion="Generated review prompt"),
            ai_helper.LLMResponse(completion="Premium portfolio review\n\nREBALANCE_NEEDED: YES"),
            ai_helper.LLMResponse(completion="Low-cost review summary"),
            ai_helper.LLMResponse(is_error=True, error_msg="Rebalance prompt failed"),
        ]
        portfolio = [models_portfolio.PortfolioHolding(ticker="CBA.AX", num_shares=100, market_price=120.0)]

        result = asyncio.run(
            ai_review_portfolio(
                portfolio=portfolio,
                country="AU",
                rebalance_plan=True,
            )
        )

        assert result is not None
        assert result.analysis == "Premium portfolio review"
        assert result.rebalance_plan == ""
        assert result.llm_error is True
        assert result.llm_error_msg == "Rebalance prompt failed"

    @patch("app.services.msai_review_portfolio.ai_helper.ai_exec_task", new_callable=AsyncMock)
    def test_preserves_review_when_rebalance_execution_fails(self, mock_ai_exec):
        from app.services.msai_review_portfolio import ai_review_portfolio

        mock_ai_exec.side_effect = [
            ai_helper.LLMResponse(completion="Generated review prompt"),
            ai_helper.LLMResponse(completion="Premium portfolio review\n\nREBALANCE_NEEDED: YES"),
            ai_helper.LLMResponse(completion="Low-cost review summary"),
            ai_helper.LLMResponse(completion="Generated rebalance prompt"),
            ai_helper.LLMResponse(is_error=True, error_msg="Rebalance execution failed"),
        ]
        portfolio = [models_portfolio.PortfolioHolding(ticker="CBA.AX", num_shares=100, market_price=120.0)]

        result = asyncio.run(
            ai_review_portfolio(
                portfolio=portfolio,
                country="AU",
                rebalance_plan=True,
            )
        )

        assert result is not None
        assert result.analysis == "Premium portfolio review"
        assert result.rebalance_plan == ""
        assert result.llm_error is True
        assert result.llm_error_msg == "Rebalance execution failed"

    @patch("app.services.msai_review_portfolio.ai_helper.ai_exec_task", new_callable=AsyncMock)
    def test_includes_portfolio_positions_in_prompt(self, mock_ai_exec):
        from app.services.msai_review_portfolio import ai_review_portfolio

        mock_ai_exec.side_effect = [
            ai_helper.LLMResponse(completion="Generated prompt"),
            ai_helper.LLMResponse(completion="Review result"),
        ]
        portfolio = [models_portfolio.PortfolioHolding(ticker="AAPL", num_shares=20, market_price=190.0, tags="growth")]

        asyncio.run(ai_review_portfolio(portfolio=portfolio, country="US"))

        first_call_args = mock_ai_exec.call_args_list[0]
        prompt_input = first_call_args[0][1]
        assert "AAPL" in prompt_input
        assert "20" in prompt_input
        assert "(growth)" in prompt_input
