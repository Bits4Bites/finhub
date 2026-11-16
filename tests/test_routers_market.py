import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app
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


def _store_with_index(index="ASX20", json_content=INDEX_JSON):
    store = services_market.MarketIndexStore()
    store.load(index, json_content)
    return store


def _loaded_countries(store):
    loaded_countries = set()
    indices_dir = Path("resources") / "indices"
    for path in indices_dir.glob("*.json"):
        for entry in json.loads(path.read_text(encoding="utf-8"))["data"]:
            exchange, code = entry["symbol"].split(":", 1)
            country = "AU" if exchange == "ASX" else "VN" if exchange in {"HNX", "HOSE"} else "US"
            if store.revert_lookup_company(country, code) is not None:
                loaded_countries.add(country)
    return loaded_countries


def test_new_market_index_store_has_no_loaded_companies():
    store = services_market.MarketIndexStore()

    assert store.revert_lookup_company("Australia", "CBA") is None


def test_store_load_builds_normalized_company_models():
    store = services_market.MarketIndexStore()
    store.load(
        "asx20",
        json.dumps(
            {
                "data": [
                    {
                        "symbol": "asx:cba",
                        "company": "Commonwealth Bank",
                    }
                ]
            }
        ),
    )

    company = store.revert_lookup_company("Australia", "cba")

    assert company is not None
    assert company.symbol == "ASX:CBA"
    assert company.name == "Commonwealth Bank"
    assert company.sector == "ASX:CBA"
    assert company.market_cap == 0
    assert company.country == "AU"


@pytest.mark.parametrize(
    ("country", "code"),
    [
        ("Atlantis", "CBA"),
        ("AU", "MISSING"),
    ],
)
def test_reverse_lookup_returns_none_for_unknown_inputs(country, code):
    store = _store_with_index()

    assert store.revert_lookup_company(country, code) is None


def test_store_reload_replaces_that_index_and_retains_other_indexes():
    store = services_market.MarketIndexStore()
    store.load(
        "SP500",
        json.dumps({"data": [{"symbol": "NASDAQ:AAPL", "company": "Apple Inc."}]}),
    )
    store.load(
        "NASDAQ100",
        json.dumps({"data": [{"symbol": "NASDAQ:MSFT", "company": "Microsoft"}]}),
    )
    store.load(
        "SP500",
        json.dumps({"data": [{"symbol": "NYSE:JNJ", "company": "Johnson & Johnson"}]}),
    )

    assert store.revert_lookup_company("US", "AAPL") is None
    assert store.revert_lookup_company("US", "JNJ").name == "Johnson & Johnson"
    assert store.revert_lookup_company("United States", "MSFT").name == "Microsoft"


@pytest.mark.parametrize(
    ("json_content", "error_type"),
    [
        ("not json", json.JSONDecodeError),
        (json.dumps({}), KeyError),
        (json.dumps({"data": [{}]}), KeyError),
        (
            json.dumps(
                {
                    "data": [
                        {
                            "symbol": "ASX:CBA",
                            "market_cap": "not-a-number",
                        }
                    ]
                }
            ),
            ValueError,
        ),
    ],
)
def test_store_load_surfaces_invalid_documents(json_content, error_type):
    store = services_market.MarketIndexStore()

    with pytest.raises(error_type):
        store.load("ASX20", json_content)


def test_load_default_indices_reads_bundled_resources(monkeypatch):
    store = services_market.MarketIndexStore()
    monkeypatch.setattr(services_market, "market_indices", store)

    services_market.load_default_indices()

    assert _loaded_countries(store) == {"AU", "US", "VN"}


def test_load_default_indices_refreshes_previously_loaded_data(monkeypatch):
    stale_json = json.dumps(
        {
            "data": [
                {
                    "symbol": "ASX:ZZZZ",
                    "company": "Stale Company",
                }
            ]
        }
    )
    store = _store_with_index("ASX20", stale_json)
    monkeypatch.setattr(services_market, "market_indices", store)

    services_market.load_default_indices()

    assert store.revert_lookup_company("AU", "ZZZZ") is None
    assert _loaded_countries(store) == {"AU", "US", "VN"}


def test_load_default_indices_continues_after_an_unreadable_resource(monkeypatch):
    store = services_market.MarketIndexStore()
    monkeypatch.setattr(services_market, "market_indices", store)
    original_read_text = services_market.Path.read_text
    failed_once = False

    def read_text(path, **kwargs):
        nonlocal failed_once
        if not failed_once:
            failed_once = True
            raise OSError("resource unavailable")
        return original_read_text(path, **kwargs)

    monkeypatch.setattr(services_market.Path, "read_text", read_text)

    services_market.load_default_indices()

    assert _loaded_countries(store) == {"AU", "US", "VN"}


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

    def read_text(_path, **_kwargs):
        if isinstance(file_result, Exception):
            raise file_result
        return file_result

    monkeypatch.setattr(services_market.Path, "read_text", read_text)

    services_market.load_default_indices()

    assert store.revert_lookup_company("AU", "CBA") is None
    assert store.revert_lookup_company("US", "AAPL") is None


def test_load_default_indices_surfaces_invalid_json(monkeypatch):
    store = services_market.MarketIndexStore()
    monkeypatch.setattr(services_market, "market_indices", store)
    monkeypatch.setattr(services_market.Path, "read_text", lambda _path, **_kwargs: "not json")

    with pytest.raises(json.JSONDecodeError):
        services_market.load_default_indices()


def test_load_default_indices_surfaces_invalid_company_records(monkeypatch):
    invalid_company_json = json.dumps(
        {
            "data": [
                {
                    "symbol": "ASX:CBA",
                    "market_cap": "not-a-number",
                }
            ]
        }
    )
    store = services_market.MarketIndexStore()
    monkeypatch.setattr(services_market, "market_indices", store)
    monkeypatch.setattr(
        services_market.Path,
        "read_text",
        lambda _path, **_kwargs: invalid_company_json,
    )

    with pytest.raises(ValueError):
        services_market.load_default_indices()


def test_get_market_index_success(monkeypatch):
    monkeypatch.setattr(services_market, "market_indices", _store_with_index())

    response = client.get("/market/index/ASX20")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.text == INDEX_JSON


def test_get_market_index_normalizes_id(monkeypatch):
    monkeypatch.setattr(services_market, "market_indices", _store_with_index())

    response = client.get("/market/index/asx20")

    assert response.status_code == 200
    assert response.text == INDEX_JSON


def test_standalone_store_does_not_publish_to_endpoint(monkeypatch):
    standalone_store = _store_with_index()
    monkeypatch.setattr(services_market, "market_indices", services_market.MarketIndexStore())

    response = client.get("/market/index/ASX20")

    assert standalone_store.revert_lookup_company("AU", "CBA") is not None
    assert response.status_code == 404


def test_get_market_index_rejects_id_outside_allowlist(monkeypatch):
    monkeypatch.setattr(
        services_market,
        "market_indices",
        _store_with_index("INTERNAL"),
    )

    response = client.get("/market/index/INTERNAL")

    assert response.status_code == 404
    assert response.json()["status"] == 404
    assert response.json()["message"]


@pytest.mark.parametrize("index_id", ["ASX20.json", "..%5CASX20"])
def test_get_market_index_rejects_path_like_id(monkeypatch, index_id):
    monkeypatch.setattr(services_market, "market_indices", services_market.MarketIndexStore())

    response = client.get(f"/market/index/{index_id}")

    assert response.status_code == 404
    assert response.json()["status"] == 404
    assert response.json()["message"]


def test_get_market_index_reports_unavailable_data(monkeypatch):
    monkeypatch.setattr(services_market, "market_indices", services_market.MarketIndexStore())

    response = client.get("/market/index/SP500")

    assert response.status_code == 404
    assert response.json()["status"] == 404
    assert response.json()["message"]


def test_get_market_index_is_public(monkeypatch):
    monkeypatch.setattr(services_market, "market_indices", _store_with_index())
    monkeypatch.setattr(config.settings_app, "api_key", "configured-api-key")

    response = client.get("/market/index/ASX20")

    assert response.status_code == 200
    assert response.text == INDEX_JSON
