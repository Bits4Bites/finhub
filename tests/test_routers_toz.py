from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.models.finhub import HistoryPoint, StockQuote

client = TestClient(app)


def _make_stock_quote(**overrides) -> StockQuote:
    """Create a StockQuote without requiring a yf.Ticker."""
    defaults = {
        "currency": "USD",
        "market_price": 2650.0,
        "market_price_change": 15.0,
        "market_price_change_percent": 0.57,
        "market_open": 2640.0,
        "market_day_high": 2660.0,
        "market_day_low": 2635.0,
        "fifty_two_week_high": 2800.0,
        "fifty_two_week_low": 2100.0,
        "market_volume": 50000,
    }
    defaults.update(overrides)
    return StockQuote.model_construct(**defaults)


def _make_history_points(n: int = 3, currency: str = "USD") -> list[HistoryPoint]:
    return [
        HistoryPoint(
            timestamp=1700000000 + i * 86400,
            timestamp_str=f"2026-01-0{i + 1} 00:00:00",
            currency=currency,
            open=100.0 + i,
            high=105.0 + i,
            low=95.0 + i,
            close=102.0 + i,
            volume=1000 + i,
        )
        for i in range(n)
    ]


class TestGoldQuoteRouter:
    @patch("app.routers.toz.toz_service.get_gold_quote")
    def test_default_currency(self, mock_get):
        mock_get.return_value = _make_stock_quote()
        resp = client.get("/toz/gold/quote")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == 200
        assert body["data"]["market_price"] == 2650.0
        mock_get.assert_called_once_with("USD")

    @patch("app.routers.toz.toz_service.get_gold_quote")
    def test_custom_currency(self, mock_get):
        mock_get.return_value = _make_stock_quote(currency="AUD", market_price=4107.5)
        resp = client.get("/toz/gold/quote?currency=AUD")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["currency"] == "AUD"
        assert body["data"]["market_price"] == 4107.5
        mock_get.assert_called_once_with("AUD")

    @patch("app.routers.toz.toz_service.get_gold_quote")
    def test_returns_null_data_when_service_returns_none(self, mock_get):
        mock_get.return_value = None
        resp = client.get("/toz/gold/quote?currency=XYZ")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == 200
        assert body.get("data") is None


class TestGoldHistoryRouter:
    @patch("app.routers.toz.toz_service.get_gold_history")
    def test_default_params(self, mock_get):
        mock_get.return_value = _make_history_points(5)
        resp = client.get("/toz/gold/history")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 5
        mock_get.assert_called_once_with("USD", 30)

    @patch("app.routers.toz.toz_service.get_gold_history")
    def test_custom_params(self, mock_get):
        mock_get.return_value = _make_history_points(7, "EUR")
        resp = client.get("/toz/gold/history?currency=EUR&days=7")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 7
        assert body["data"][0]["currency"] == "EUR"
        mock_get.assert_called_once_with("EUR", 7)

    @patch("app.routers.toz.toz_service.get_gold_history")
    def test_returns_null_data_when_service_returns_none(self, mock_get):
        mock_get.return_value = None
        resp = client.get("/toz/gold/history?currency=XYZ")
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("data") is None


class TestSilverQuoteRouter:
    @patch("app.routers.toz.toz_service.get_silver_quote")
    def test_default_currency(self, mock_get):
        mock_get.return_value = _make_stock_quote(market_price=31.5)
        resp = client.get("/toz/silver/quote")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["market_price"] == 31.5
        mock_get.assert_called_once_with("USD")

    @patch("app.routers.toz.toz_service.get_silver_quote")
    def test_custom_currency(self, mock_get):
        mock_get.return_value = _make_stock_quote(currency="AUD", market_price=48.8)
        resp = client.get("/toz/silver/quote?currency=AUD")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["currency"] == "AUD"
        mock_get.assert_called_once_with("AUD")

    @patch("app.routers.toz.toz_service.get_silver_quote")
    def test_returns_null_data_when_service_returns_none(self, mock_get):
        mock_get.return_value = None
        resp = client.get("/toz/silver/quote?currency=XYZ")
        assert resp.status_code == 200
        assert resp.json().get("data") is None


class TestSilverHistoryRouter:
    @patch("app.routers.toz.toz_service.get_silver_history")
    def test_default_params(self, mock_get):
        mock_get.return_value = _make_history_points(4)
        resp = client.get("/toz/silver/history")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 4
        mock_get.assert_called_once_with("USD", 30)

    @patch("app.routers.toz.toz_service.get_silver_history")
    def test_custom_params(self, mock_get):
        mock_get.return_value = _make_history_points(2, "AUD")
        resp = client.get("/toz/silver/history?currency=AUD&days=90")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 2
        mock_get.assert_called_once_with("AUD", 90)

    @patch("app.routers.toz.toz_service.get_silver_history")
    def test_returns_null_data_when_service_returns_none(self, mock_get):
        mock_get.return_value = None
        resp = client.get("/toz/silver/history?currency=XYZ")
        assert resp.status_code == 200
        assert resp.json().get("data") is None
