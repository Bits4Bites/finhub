from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app
from app.models.finhub import StockQuote

client = TestClient(app)

# A protected endpoint (any router endpoint works since all routers are guarded).
PROTECTED_URL = "/toz/gold/quote"
CONFIGURED_KEY = "super-secret-key"


def _make_stock_quote() -> StockQuote:
    return StockQuote.model_construct(currency="USD", market_price=2650.0)


@pytest.fixture
def configured_api_key(monkeypatch):
    """Configure a server-side API key for the duration of a test."""
    monkeypatch.setattr(config.settings_app, "api_key", CONFIGURED_KEY)
    return CONFIGURED_KEY


class TestApiKeyAuth:
    def test_missing_key_is_rejected(self, configured_api_key):
        response = client.get(PROTECTED_URL)
        assert response.status_code == 401
        body = response.json()
        assert body["status"] == 401
        assert "API key" in body["message"]

    def test_invalid_key_is_rejected(self, configured_api_key):
        response = client.get(PROTECTED_URL, headers={"X-API-Key": "wrong-key"})
        assert response.status_code == 401
        assert response.json()["status"] == 401

    def test_valid_key_is_accepted(self, configured_api_key):
        with patch("app.services.toz.get_gold_quote", return_value=_make_stock_quote()):
            response = client.get(PROTECTED_URL, headers={"X-API-Key": CONFIGURED_KEY})
        assert response.status_code == 200
        assert response.json()["status"] == 200

    @pytest.mark.parametrize("header_name", ["X-API-Key", "x-api-key", "X-Api-Key", "x-API-KEY"])
    def test_header_name_is_case_insensitive(self, configured_api_key, header_name):
        with patch("app.services.toz.get_gold_quote", return_value=_make_stock_quote()):
            response = client.get(PROTECTED_URL, headers={header_name: CONFIGURED_KEY})
        assert response.status_code == 200

    def test_no_configured_key_allows_access(self, monkeypatch):
        # Fail-open: when no key is configured, requests are allowed without a header.
        monkeypatch.setattr(config.settings_app, "api_key", "")
        with patch("app.services.toz.get_gold_quote", return_value=_make_stock_quote()):
            response = client.get(PROTECTED_URL)
        assert response.status_code == 200

    def test_open_endpoints_do_not_require_key(self, configured_api_key):
        # Root and health endpoints are not protected.
        assert client.get("/").status_code == 200
        assert client.get("/health").status_code == 200
