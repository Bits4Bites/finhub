from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app
from app.routers import market

client = TestClient(app)
INDEX_JSON = """{
    "date": "2026-07-28",
    "data": [
        {
            "symbol": "ASX:CBA",
            "company": "COMMONWEALTH BANK OF AUSTRALIA",
            "sector": "Banks"
        }
    ]
}"""

EXPECTED_INDEX_IDS = frozenset(
    {
        "ASX20",
        "ASX50",
        "ASX100",
        "ASX200",
        "ASX300",
        "HNX30",
        "NASDAQ100",
        "SP400",
        "SP500",
        "SP600",
        "VN30",
        "VN100",
    }
)


def test_market_index_allowlist_is_explicit():
    assert market.SUPPORTED_INDEX_IDS == EXPECTED_INDEX_IDS


def test_market_index_files_are_preloaded_verbatim():
    expected_json = Path("resources/indices/asx20.json").read_text(encoding="utf-8")

    assert config.market_indices.raw_json["ASX20"] == expected_json


@patch("app.routers.market.config.market_indices")
def test_get_market_index_success(mock_market_indices):
    mock_market_indices.raw_json = {"ASX20": INDEX_JSON}

    response = client.get("/market/index/ASX20")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.text == INDEX_JSON


@patch("app.routers.market.config.market_indices")
def test_get_market_index_normalizes_id(mock_market_indices):
    mock_market_indices.raw_json = {"ASX20": INDEX_JSON}

    response = client.get("/market/index/asx20")

    assert response.status_code == 200
    assert response.text == INDEX_JSON


@patch("app.routers.market.config.market_indices")
def test_get_market_index_rejects_id_outside_allowlist(mock_market_indices):
    mock_market_indices.raw_json = {"INTERNAL": INDEX_JSON}

    response = client.get("/market/index/INTERNAL")

    assert response.status_code == 404
    assert response.json() == {"status": 404, "message": "Market index not found"}


@pytest.mark.parametrize("index_id", ["ASX20.json", "..%5CASX20"])
def test_get_market_index_rejects_path_like_id(index_id):
    response = client.get(f"/market/index/{index_id}")

    assert response.status_code == 404
    assert response.json() == {"status": 404, "message": "Market index not found"}


@patch("app.routers.market.config.market_indices")
def test_get_market_index_reports_missing_cache(mock_market_indices):
    mock_market_indices.raw_json = {}

    response = client.get("/market/index/SP500")

    assert response.status_code == 404
    assert response.json() == {"status": 404, "message": "Market index not found"}


@patch("app.routers.market.config.market_indices")
def test_get_market_index_is_public(mock_market_indices, monkeypatch):
    mock_market_indices.raw_json = {"ASX20": INDEX_JSON}
    monkeypatch.setattr(config.settings_app, "api_key", "configured-api-key")

    response = client.get("/market/index/ASX20")

    assert response.status_code == 200
    assert response.text == INDEX_JSON
