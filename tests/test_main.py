import asyncio
from unittest.mock import MagicMock, patch

from app import config, main


def _make_entry(idx: int) -> dict:
    return {
        "id": idx,
        "ip": f"10.0.0.{idx}",
        "port": 8000 + idx,
        "protocol": "http",
        "anonymity": "elite",
        "speed": 1.5,
        "https": 0,
        "country": "US",
        "city": "City",
        "connect_string": f"http://10.0.0.{idx}:{8000 + idx}",
    }


def _make_response(entries: list[dict]) -> MagicMock:
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"data": {"data": entries}}
    return response


def test_load_proxies_task_picks_ten():
    entries = [_make_entry(i) for i in range(25)]
    config.settings_finhub_proxy.http_proxies = None
    with patch.object(main.requests, "get", return_value=_make_response(entries)):
        asyncio.run(main._load_proxies_task())

    proxies = config.settings_finhub_proxy.http_proxies
    assert proxies is not None
    assert len(proxies) == 10
    assert all(isinstance(p, config.HttpProxy) for p in proxies)


def test_load_proxies_task_fewer_than_ten():
    entries = [_make_entry(i) for i in range(3)]
    config.settings_finhub_proxy.http_proxies = None
    with patch.object(main.requests, "get", return_value=_make_response(entries)):
        asyncio.run(main._load_proxies_task())

    assert len(config.settings_finhub_proxy.http_proxies) == 3


def test_load_proxies_task_empty_keeps_existing():
    existing = [config.HttpProxy(id=99)]
    config.settings_finhub_proxy.http_proxies = existing
    with patch.object(main.requests, "get", return_value=_make_response([])):
        asyncio.run(main._load_proxies_task())

    assert config.settings_finhub_proxy.http_proxies is existing


def test_load_proxies_task_error_keeps_existing():
    existing = [config.HttpProxy(id=42)]
    config.settings_finhub_proxy.http_proxies = existing
    with patch.object(main.requests, "get", side_effect=RuntimeError("boom")):
        asyncio.run(main._load_proxies_task())

    assert config.settings_finhub_proxy.http_proxies is existing
