import pytest

from app import config


@pytest.fixture(autouse=True)
def disable_api_auth(monkeypatch):
    monkeypatch.setattr(config.settings_app, "api_key", "")
