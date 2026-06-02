"""Unit tests for app.routers.events module."""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.models.event import ListingEvent, UpcomingDividendEvent, UpcomingEarningsEvent

client = TestClient(app)


# ===========================================================================
# Tests for GET /events/upcoming_dividends
# ===========================================================================


class TestUpcomingDividends:
    @patch("app.routers.events.services_event.get_asx_upcoming_dividends_events", new_callable=AsyncMock)
    def test_au_returns_dividends(self, mock_get):
        event = UpcomingDividendEvent.model_construct(
            symbol="ASX:CBA",
            company_name="CBA",
            date="2026-06-10",
            amount=2.0,
            dividend_yield=0.03,
            payment_date="2026-07-01",
        )
        mock_get.return_value = [event]

        resp = client.get("/events/upcoming_dividends", params={"country": "AU", "index": ""})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == 200
        assert body["message"] == "ok"
        assert len(body["data"]) == 1
        assert body["data"][0]["symbol"] == "ASX:CBA"
        mock_get.assert_called_once_with("")

    @patch("app.routers.events.services_event.get_us_upcoming_dividends_events", new_callable=AsyncMock)
    def test_us_returns_dividends(self, mock_get):
        mock_get.return_value = []

        resp = client.get("/events/upcoming_dividends", params={"country": "US", "index": "SP500"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == 200
        assert body["data"] == []
        mock_get.assert_called_once_with("SP500")

    @patch("app.routers.events.services_event.get_vn_upcoming_dividends_events", new_callable=AsyncMock)
    def test_vn_returns_dividends(self, mock_get):
        mock_get.return_value = []

        resp = client.get("/events/upcoming_dividends", params={"country": "VN", "index": ""})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == 200
        mock_get.assert_called_once_with("")

    def test_unsupported_country_returns_501(self):
        resp = client.get("/events/upcoming_dividends", params={"country": "JP", "index": ""})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == 501
        assert "Unsupported" in body["message"]

    def test_missing_country_returns_422(self):
        resp = client.get("/events/upcoming_dividends")
        assert resp.status_code == 422


# ===========================================================================
# Tests for GET /events/upcoming_earnings
# ===========================================================================


class TestUpcomingEarnings:
    @patch("app.routers.events.services_event.get_asx_upcoming_earnings_events", new_callable=AsyncMock)
    def test_au_returns_earnings(self, mock_get):
        event = UpcomingEarningsEvent.model_construct(
            symbol="ASX:BHP",
            company_name="BHP Group",
            date="2026-08-15",
        )
        mock_get.return_value = [event]

        resp = client.get("/events/upcoming_earnings", params={"country": "AU", "index": ""})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == 200
        assert len(body["data"]) == 1
        assert body["data"][0]["symbol"] == "ASX:BHP"
        mock_get.assert_called_once_with("")

    @patch("app.routers.events.services_event.get_us_upcoming_earnings_events", new_callable=AsyncMock)
    def test_us_returns_earnings(self, mock_get):
        mock_get.return_value = []

        resp = client.get("/events/upcoming_earnings", params={"country": "US", "index": "NASDAQ100"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == 200
        assert body["data"] == []
        mock_get.assert_called_once_with("NASDAQ100")

    def test_unsupported_country_returns_501(self):
        resp = client.get("/events/upcoming_earnings", params={"country": "JP", "index": ""})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == 501
        assert "Unsupported" in body["message"]

    def test_missing_country_returns_422(self):
        resp = client.get("/events/upcoming_earnings")
        assert resp.status_code == 422


# ===========================================================================
# Tests for GET /events/new_listings
# ===========================================================================


class TestNewListings:
    @patch("app.routers.events.services_asx_listings.ai_get_asx_new_listings", new_callable=AsyncMock)
    def test_au_returns_listings(self, mock_get):
        event = ListingEvent.model_construct(
            symbol="ASX:XYZ",
            company_name="XYZ Corp",
            date="2026-06-20",
            price=2.5,
        )
        mock_get.return_value = [event]

        resp = client.get("/events/new_listings", params={"country": "AU"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == 200
        assert body["message"] == "ok"
        assert len(body["data"]) == 1
        assert body["data"][0]["symbol"] == "ASX:XYZ"
        mock_get.assert_called_once()

    def test_unsupported_country_returns_501(self):
        resp = client.get("/events/new_listings", params={"country": "JP"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == 501
        assert "Unsupported" in body["message"]

    @patch("app.routers.events.services_asx_listings.ai_get_asx_new_listings", new_callable=AsyncMock)
    def test_empty_country_defaults_unsupported(self, mock_get):
        resp = client.get("/events/new_listings", params={"country": ""})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == 501
