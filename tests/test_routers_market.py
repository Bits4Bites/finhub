import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app
from app.routers import market
from app.services import market as services_market

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

    assert services_market.market_indices.raw_json["ASX20"] == expected_json


def test_load_default_indices_populates_the_process_store(monkeypatch):
    store = services_market.MarketIndexStore()
    monkeypatch.setattr(services_market, "market_indices", store)
    monkeypatch.setattr(services_market, "_INDEX_FILES", (("ASX20", "asx20.json"),))
    monkeypatch.setattr(services_market.Path, "read_text", MagicMock(return_value=INDEX_JSON))

    services_market.load_default_indices()

    assert store.raw_json["ASX20"] == INDEX_JSON
    assert "ASX:CBA" in store.indices["ASX20"]


@pytest.mark.parametrize(
    "file_result",
    [
        "",
        FileNotFoundError(),
        PermissionError(),
        OSError(),
    ],
)
def test_load_default_indices_skips_unavailable_resources(monkeypatch, file_result):
    store = services_market.MarketIndexStore()
    monkeypatch.setattr(services_market, "market_indices", store)
    monkeypatch.setattr(services_market, "_INDEX_FILES", (("ASX20", "asx20.json"),))
    read_text = MagicMock(return_value=file_result)
    if isinstance(file_result, Exception):
        read_text.side_effect = file_result
    monkeypatch.setattr(services_market.Path, "read_text", read_text)

    services_market.load_default_indices()

    assert store.raw_json == {}
    assert store.indices == {}


def test_load_default_indices_propagates_invalid_index_data(monkeypatch):
    store = services_market.MarketIndexStore()
    monkeypatch.setattr(services_market, "market_indices", store)
    monkeypatch.setattr(services_market, "_INDEX_FILES", (("ASX20", "asx20.json"),))
    monkeypatch.setattr(services_market.Path, "read_text", MagicMock(return_value="not json"))

    with pytest.raises(json.JSONDecodeError):
        services_market.load_default_indices()


def test_load_default_indices_continues_after_an_unreadable_resource(monkeypatch):
    store = services_market.MarketIndexStore()
    monkeypatch.setattr(services_market, "market_indices", store)
    monkeypatch.setattr(
        services_market,
        "_INDEX_FILES",
        (("ASX20", "asx20.json"), ("ASX50", "asx50.json")),
    )

    def read_text(path, **_kwargs):
        if path.name == "asx20.json":
            raise OSError("storage unavailable")
        return INDEX_JSON

    monkeypatch.setattr(services_market.Path, "read_text", read_text)

    services_market.load_default_indices()

    assert "ASX20" not in store.indices
    assert store.raw_json["ASX50"] == INDEX_JSON
    assert "ASX:CBA" in store.indices["ASX50"]


def test_load_default_indices_propagates_invalid_company_records(monkeypatch):
    invalid_company_json = json.dumps(
        {
            "data": [
                {
                    "symbol": "ASX:CBA",
                    "company": "COMMONWEALTH BANK OF AUSTRALIA",
                    "market_cap": "not-a-number",
                }
            ]
        }
    )
    store = services_market.MarketIndexStore()
    monkeypatch.setattr(services_market, "market_indices", store)
    monkeypatch.setattr(services_market, "_INDEX_FILES", (("ASX20", "asx20.json"),))
    monkeypatch.setattr(
        services_market.Path,
        "read_text",
        MagicMock(return_value=invalid_company_json),
    )

    with pytest.raises(ValueError):
        services_market.load_default_indices()


def test_load_default_indices_replaces_previous_successful_data(monkeypatch):
    first_json = INDEX_JSON
    second_json = json.dumps(
        {
            "data": [
                {
                    "symbol": "ASX:BHP",
                    "company": "BHP GROUP LIMITED",
                    "sector": "Materials",
                }
            ]
        }
    )
    contents = iter((first_json, second_json))
    store = services_market.MarketIndexStore()
    monkeypatch.setattr(services_market, "market_indices", store)
    monkeypatch.setattr(services_market, "_INDEX_FILES", (("ASX20", "asx20.json"),))
    monkeypatch.setattr(
        services_market.Path,
        "read_text",
        lambda _path, **_kwargs: next(contents),
    )

    services_market.load_default_indices()
    services_market.load_default_indices()

    assert store.raw_json["ASX20"] == second_json
    assert set(store.indices["ASX20"]) == {"ASX:BHP"}
    assert store.revert_lookup_company("AU", "CBA") is None
    assert store.revert_lookup_company("AU", "BHP").name == "BHP GROUP LIMITED"


def test_reverse_lookup_aggregates_indexes_and_rebuilds_replaced_index():
    sp500_json = json.dumps(
        {
            "data": [
                {
                    "symbol": "NASDAQ:AAPL",
                    "company": "Apple Inc.",
                }
            ]
        }
    )
    nasdaq100_json = json.dumps(
        {
            "data": [
                {
                    "symbol": "NASDAQ:MSFT",
                    "company": "Microsoft Corporation",
                }
            ]
        }
    )
    replacement_sp500_json = json.dumps(
        {
            "data": [
                {
                    "symbol": "NYSE:JNJ",
                    "company": "Johnson & Johnson",
                }
            ]
        }
    )
    store = services_market.MarketIndexStore()

    store.load("SP500", sp500_json)
    store.load("NASDAQ100", nasdaq100_json)

    assert store.revert_lookup_company("US", "AAPL").name == "Apple Inc."
    assert store.revert_lookup_company("United States", "MSFT").name == "Microsoft Corporation"

    store.load("SP500", replacement_sp500_json)

    assert store.revert_lookup_company("US", "AAPL") is None
    assert store.revert_lookup_company("US", "JNJ").name == "Johnson & Johnson"
    assert store.revert_lookup_company("US", "MSFT").name == "Microsoft Corporation"


@patch("app.routers.market.services_market.market_indices")
def test_get_market_index_success(mock_market_indices):
    mock_market_indices.raw_json = {"ASX20": INDEX_JSON}

    response = client.get("/market/index/ASX20")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.text == INDEX_JSON


@patch("app.routers.market.services_market.market_indices")
def test_get_market_index_normalizes_id(mock_market_indices):
    mock_market_indices.raw_json = {"ASX20": INDEX_JSON}

    response = client.get("/market/index/asx20")

    assert response.status_code == 200
    assert response.text == INDEX_JSON


@patch("app.routers.market.services_market.market_indices")
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


@patch("app.routers.market.services_market.market_indices")
def test_get_market_index_reports_missing_cache(mock_market_indices):
    mock_market_indices.raw_json = {}

    response = client.get("/market/index/SP500")

    assert response.status_code == 404
    assert response.json() == {"status": 404, "message": "Market index not found"}


@patch("app.routers.market.services_market.market_indices")
def test_get_market_index_is_public(mock_market_indices, monkeypatch):
    mock_market_indices.raw_json = {"ASX20": INDEX_JSON}
    monkeypatch.setattr(config.settings_app, "api_key", "configured-api-key")

    response = client.get("/market/index/ASX20")

    assert response.status_code == 200
    assert response.text == INDEX_JSON
