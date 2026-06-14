"""Unit tests for app.routers.ai."""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.models.ai import AnalysisResult
from app.models.event import DividendEventAnalysis

client = TestClient(app)


# ===========================================================================
# GET /ai/vendors
# ===========================================================================


class TestGetVendors:
    """Tests for GET /ai/vendors endpoint."""

    def test_returns_vendors_list(self):
        resp = client.get("/ai/vendors")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == 200
        assert body["message"] == "ok"
        assert isinstance(body["data"], dict)


# ===========================================================================
# GET /ai/analyze_dividend_event
# ===========================================================================


class TestAnalyzeDividendEvent:
    """Tests for GET /ai/analyze_dividend_event endpoint."""

    @patch(
        "app.routers.ai.service_analyze_div_event.ai_analyze_div_event",
        new_callable=AsyncMock,
    )
    def test_success(self, mock_analyze):
        mock_analyze.return_value = DividendEventAnalysis(
            symbol="CBA.AX",
            price=120.0,
            div_amount=2.5,
        )
        resp = client.get(
            "/ai/analyze_dividend_event",
            params={"symbol": "ASX:CBA", "ex_date": "2025-08-15", "div_amount": 2.5},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == 200
        assert body["data"]["symbol"] == "CBA.AX"
        assert body["data"]["div_amount"] == 2.5
        mock_analyze.assert_called_once_with(
            symbol="ASX:CBA",
            ex_date="2025-08-15",
            div_amount=2.5,
            intent=mock_analyze.call_args.kwargs["intent"],
        )

    @patch(
        "app.routers.ai.service_analyze_div_event.ai_analyze_div_event",
        new_callable=AsyncMock,
    )
    def test_returns_400_when_service_returns_none(self, mock_analyze):
        mock_analyze.return_value = None
        resp = client.get(
            "/ai/analyze_dividend_event",
            params={"symbol": "INVALID", "ex_date": "2025-08-15", "div_amount": 1.0},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == 400
        assert "Invalid" in body["message"]

    def test_missing_params_returns_422(self):
        resp = client.get("/ai/analyze_dividend_event")
        assert resp.status_code == 422


# ===========================================================================
# POST /ai/analyze_ticker
# ===========================================================================


class TestAnalyzeTicker:
    """Tests for POST /ai/analyze_ticker endpoint."""

    @patch(
        "app.routers.ai.service_analyze_ticker.ai_analyze_ticker",
        new_callable=AsyncMock,
    )
    def test_success(self, mock_analyze):
        mock_analyze.return_value = AnalysisResult(
            llm_error=False,
            analysis="AAPL looks bullish",
        )
        resp = client.post("/ai/analyze_ticker", json={"symbol": "NASDAQ:AAPL"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == 200
        assert body["data"]["analysis"] == "AAPL looks bullish"
        mock_analyze.assert_called_once()
        assert mock_analyze.call_args.kwargs["symbol"] == "NASDAQ:AAPL"

    @patch(
        "app.routers.ai.service_analyze_ticker.ai_analyze_ticker",
        new_callable=AsyncMock,
    )
    def test_returns_400_when_service_returns_none(self, mock_analyze):
        mock_analyze.return_value = None
        resp = client.post("/ai/analyze_ticker", json={"symbol": "INVALID"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == 400
        assert "Invalid" in body["message"] or "failed" in body["message"]

    @patch(
        "app.routers.ai.service_analyze_ticker.ai_analyze_ticker",
        new_callable=AsyncMock,
    )
    def test_passes_intent_to_service(self, mock_analyze):
        mock_analyze.return_value = AnalysisResult(llm_error=False, analysis="result")
        resp = client.post(
            "/ai/analyze_ticker",
            json={"symbol": "ASX:CBA", "intent": "focus on dividends"},
        )
        assert resp.status_code == 200
        mock_analyze.assert_called_once_with(symbol="ASX:CBA", intent="focus on dividends")


# ===========================================================================
# POST /ai/build_portfolio
# ===========================================================================


class TestBuildPortfolio:
    """Tests for POST /ai/build_portfolio endpoint."""

    @patch(
        "app.routers.ai.service_build_portfolio.ai_build_portfolio",
        new_callable=AsyncMock,
    )
    def test_success(self, mock_build):
        mock_build.return_value = AnalysisResult(llm_error=False, analysis="Portfolio: ...")
        resp = client.post("/ai/build_portfolio", json={"country": "AU"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == 200
        assert body["data"]["analysis"] == "Portfolio: ..."

    @patch(
        "app.routers.ai.service_build_portfolio.ai_build_portfolio",
        new_callable=AsyncMock,
    )
    def test_returns_400_when_service_returns_none(self, mock_build):
        mock_build.return_value = None
        resp = client.post("/ai/build_portfolio", json={"country": "AU"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == 400

    @patch(
        "app.routers.ai.service_build_portfolio.ai_build_portfolio",
        new_callable=AsyncMock,
    )
    def test_passes_existing_positions(self, mock_build):
        mock_build.return_value = AnalysisResult(llm_error=False, analysis="result")
        positions = [{"ticker": "AAPL", "num_shares": 10, "market_price": 150.0}]
        resp = client.post(
            "/ai/build_portfolio",
            json={"country": "US", "current_allocation": positions},
        )
        assert resp.status_code == 200
        call_kwargs = mock_build.call_args.kwargs
        assert len(call_kwargs["existing_positions"]) == 1
        assert call_kwargs["existing_positions"][0].ticker == "AAPL"


# ===========================================================================
# POST /ai/analyze_portfolio
# ===========================================================================


class TestSpotlightPortfolio:
    """Tests for POST /ai/spotlight_portfolio endpoint."""

    @patch(
        "app.routers.ai.service_spotlight_portfolio.ai_spotlight_portfolio",
        new_callable=AsyncMock,
    )
    def test_success(self, mock_spotlight):
        mock_spotlight.return_value = AnalysisResult(llm_error=False, analysis="Immediate risks and actions")

        resp = client.post(
            "/ai/spotlight_portfolio",
            json={
                "country": "AU",
                "current_allocation": [{"ticker": "CBA.AX", "num_shares": 100, "market_price": 120.0}],
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == 200
        assert body["data"]["analysis"] == "Immediate risks and actions"
        mock_spotlight.assert_called_once()


class TestAnalyzePortfolio:
    """Tests for POST /ai/analyze_portfolio endpoint."""

    @patch(
        "app.routers.ai.service_review_portfolio.ai_review_portfolio",
        new_callable=AsyncMock,
    )
    def test_with_positions_calls_review(self, mock_review):
        mock_review.return_value = AnalysisResult(llm_error=False, analysis="Well diversified")
        positions = [{"ticker": "CBA.AX", "num_shares": 100, "market_price": 120.0}]
        resp = client.post(
            "/ai/analyze_portfolio",
            json={"country": "AU", "current_allocation": positions},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == 200
        assert body["data"]["analysis"] == "Well diversified"
        mock_review.assert_called_once()

    @patch(
        "app.routers.ai.service_build_portfolio.ai_build_portfolio",
        new_callable=AsyncMock,
    )
    def test_without_positions_calls_build(self, mock_build):
        mock_build.return_value = AnalysisResult(llm_error=False, analysis="New portfolio")
        resp = client.post(
            "/ai/analyze_portfolio",
            json={"country": "US", "current_allocation": []},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["analysis"] == "New portfolio"
        mock_build.assert_called_once()

    @patch(
        "app.routers.ai.service_build_portfolio.ai_build_portfolio",
        new_callable=AsyncMock,
    )
    def test_returns_400_when_service_fails(self, mock_build):
        mock_build.return_value = None
        resp = client.post(
            "/ai/analyze_portfolio",
            json={"country": "AU"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == 400

    @patch(
        "app.routers.ai.service_review_portfolio.ai_review_portfolio",
        new_callable=AsyncMock,
    )
    def test_passes_investor_theme(self, mock_review):
        mock_review.return_value = AnalysisResult(llm_error=False, analysis="result")
        positions = [{"ticker": "BHP.AX", "num_shares": 50, "market_price": 45.0}]
        resp = client.post(
            "/ai/analyze_portfolio",
            json={
                "country": "AU",
                "current_allocation": positions,
                "investor_theme": "Growth focused",
            },
        )
        assert resp.status_code == 200
        assert mock_review.call_args.kwargs["investor_theme"] == "Growth focused"
