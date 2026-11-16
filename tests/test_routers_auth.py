import datetime

import pytest
from fastapi.testclient import TestClient

from app import config, version
from app.main import APP_DESCRIPTION, APP_NAME, app

client = TestClient(app)

CONFIGURED_KEY = "super-secret-key"
AUTH_FAILURE = {"status": 401, "message": "Invalid or missing API key"}


@pytest.fixture
def configured_api_key(monkeypatch):
    monkeypatch.setattr(config.settings_app, "api_key", CONFIGURED_KEY)
    return CONFIGURED_KEY


@pytest.mark.parametrize(
    ("path", "params"),
    [
        ("/stocks/quotes", {"symbols": "NASDAQ:AAPL"}),
        ("/events/new_listings", None),
        ("/ai/vendors", None),
        ("/toz/gold/quote", None),
    ],
)
@pytest.mark.parametrize("header_value", [None, "wrong-key"])
def test_documented_protected_prefixes_reject_missing_or_invalid_keys(
    configured_api_key,
    path,
    params,
    header_value,
):
    headers = {} if header_value is None else {"X-API-Key": header_value}

    response = client.get(path, params=params, headers=headers)

    assert response.status_code == 401
    assert response.json() == AUTH_FAILURE


@pytest.mark.parametrize("header_name", ["X-API-Key", "x-api-key", "X-Api-Key", "x-API-KEY"])
def test_api_key_header_name_is_case_insensitive(configured_api_key, header_name):
    response = client.get("/ai/vendors", headers={header_name: configured_api_key})

    assert response.status_code == 200


def test_empty_server_key_disables_authentication(monkeypatch):
    monkeypatch.setattr(config.settings_app, "api_key", "")

    response = client.get("/ai/vendors")

    assert response.status_code == 200


def test_unicode_configured_key_rejects_an_invalid_http_key_normally(monkeypatch):
    monkeypatch.setattr(config.settings_app, "api_key", "clé-secrète")

    response = client.get("/ai/vendors", headers={"X-API-Key": "incorrect"})

    assert response.status_code == 401
    assert response.json() == AUTH_FAILURE


def test_root_and_health_return_their_complete_public_bodies(configured_api_key):
    root_response = client.get("/")
    health_response = client.get("/health")

    assert root_response.status_code == 200
    assert root_response.json() == {
        "status": 200,
        "message": "Welcome to the FinHub API!",
    }
    assert health_response.status_code == 200
    assert health_response.json() == {"status": 200, "message": "ok"}


def test_info_returns_complete_identity_and_current_server_local_time(configured_api_key):
    before = datetime.datetime.now().replace(microsecond=0)

    response = client.get("/info")

    after = datetime.datetime.now().replace(microsecond=0)
    assert response.status_code == 200
    body = response.json()
    assert body == {
        "status": 200,
        "message": "ok",
        "data": {
            "app_name": APP_NAME,
            "app_description": APP_DESCRIPTION,
            "version": version.VERSION,
            "server_time": body["data"]["server_time"],
        },
    }
    observed = datetime.datetime.strptime(body["data"]["server_time"], "%Y-%m-%d %H:%M:%S")
    assert before <= observed <= after


def test_market_prefix_is_open_when_authentication_is_configured(configured_api_key):
    response = client.get("/market/index/NOT_SUPPORTED")

    assert response.status_code == 404
    assert response.json()["status"] == 404
