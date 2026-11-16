import json

import httpx2
import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app
from app.routers import proxy_handler

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_proxy_settings(monkeypatch):
    monkeypatch.setattr(config.settings_finhub_proxy, "proxy_mode", "None")
    monkeypatch.setattr(config.settings_finhub_proxy, "url_web_crawl_node", "")
    monkeypatch.setattr(config.settings_finhub_proxy, "url_ai_task_node", "")


@pytest.mark.parametrize(
    ("method", "path", "request_kwargs", "node_attribute", "node_url", "expected_location"),
    [
        (
            "get",
            "/events/upcoming_earnings",
            {"params": {"country": "US", "index": "SP500"}},
            "url_web_crawl_node",
            "https://proxy.example/finhub?source=primary#results",
            "https://proxy.example/finhub/events/upcoming_earnings?source=primary&country=US&index=SP500#results",
        ),
        (
            "post",
            "/ai/analyze_ticker",
            {"json": {"symbol": "NASDAQ:AAPL"}},
            "url_ai_task_node",
            "https://proxy.example/finhub/",
            "https://proxy.example/finhub/ai/analyze_ticker",
        ),
    ],
)
def test_redirect_mode_preserves_public_method_path_query_base_path_and_fragment(
    monkeypatch,
    method,
    path,
    request_kwargs,
    node_attribute,
    node_url,
    expected_location,
):
    monkeypatch.setattr(config.settings_finhub_proxy, "proxy_mode", "redirect")
    monkeypatch.setattr(config.settings_finhub_proxy, node_attribute, node_url)

    response = client.request(method, path, follow_redirects=False, **request_kwargs)

    assert response.status_code == 307
    assert response.headers["location"] == expected_location


@pytest.mark.parametrize("proxy_mode", ["None", "none", "unsupported"])
def test_disabled_or_unknown_proxy_mode_executes_the_local_endpoint(monkeypatch, proxy_mode):
    monkeypatch.setattr(config.settings_finhub_proxy, "proxy_mode", proxy_mode)
    monkeypatch.setattr(config.settings_finhub_proxy, "url_ai_task_node", "https://proxy.example")

    response = client.get("/events/new_listings", params={"country": "unsupported"})

    assert response.status_code == 200
    assert response.json()["status"] == 501


def test_empty_node_url_disables_forwarding_before_timeout_validation(monkeypatch):
    monkeypatch.setattr(config.settings_finhub_proxy, "proxy_mode", "Forward")
    monkeypatch.setattr(config.settings_finhub_proxy, "url_ai_task_node", "")

    response = client.get(
        "/events/new_listings",
        params={"country": "unsupported"},
        headers={"X-FinHub-Forward-Timeout-Seconds": "invalid"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == 501


class _ReflectingAsyncClient:
    def __init__(self, *, follow_redirects, timeout):
        self.follow_redirects = follow_redirects
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None

    async def request(self, method, url, *, content, headers):
        forwarded_headers = {name.decode("latin-1"): value.decode("latin-1") for name, value in headers}
        reflected = {
            "method": method,
            "url": url,
            "body": content.decode(),
            "headers": forwarded_headers,
            "follow_redirects": self.follow_redirects,
            "read_timeout": self.timeout.read,
        }
        return httpx2.Response(
            status_code=201,
            headers=[
                ("content-type", "application/json"),
                ("content-length", "999"),
                ("set-cookie", "first=1"),
                ("set-cookie", "second=2"),
                ("connection", "x-upstream"),
                ("x-upstream", "remove"),
                ("x-result", "preserve"),
            ],
            content=json.dumps(reflected).encode(),
        )


@pytest.mark.parametrize(("timeout_header", "expected_timeout"), [(None, 600.0), ("0.1", 0.1), ("86400", 86400.0)])
def test_forward_mode_relays_public_request_and_response_semantics(
    monkeypatch,
    timeout_header,
    expected_timeout,
):
    monkeypatch.setattr(config.settings_finhub_proxy, "proxy_mode", "fOrWaRd")
    monkeypatch.setattr(
        config.settings_finhub_proxy,
        "url_ai_task_node",
        "https://proxy.example/finhub?source=primary",
    )
    monkeypatch.setattr(proxy_handler.httpx2, "AsyncClient", _ReflectingAsyncClient)
    headers = {
        "connection": "keep-alive, x-remove",
        "x-remove": "remove",
        "x-client": "preserve",
        "accept-encoding": "gzip",
    }
    if timeout_header is not None:
        headers["X-FinHub-Forward-Timeout-Seconds"] = timeout_header

    response = client.post(
        "/ai/analyze_ticker",
        json={"symbol": "NASDAQ:AAPL"},
        headers=headers,
    )

    assert response.status_code == 201
    reflected = response.json()
    assert reflected["method"] == "POST"
    assert reflected["url"] == "https://proxy.example/finhub/ai/analyze_ticker?source=primary"
    assert json.loads(reflected["body"]) == {"symbol": "NASDAQ:AAPL"}
    assert reflected["follow_redirects"] is False
    assert reflected["read_timeout"] == expected_timeout
    assert reflected["headers"]["content-type"] == "application/json"
    assert reflected["headers"]["x-client"] == "preserve"
    assert reflected["headers"]["accept-encoding"] == "identity"
    assert "host" not in reflected["headers"]
    assert "content-length" not in reflected["headers"]
    assert "connection" not in reflected["headers"]
    assert "x-remove" not in reflected["headers"]
    assert response.headers["x-result"] == "preserve"
    assert response.headers.get_list("set-cookie") == ["first=1", "second=2"]
    assert "connection" not in response.headers
    assert "x-upstream" not in response.headers
    assert response.headers["content-length"] == str(len(response.content))


@pytest.mark.parametrize("header_value", ["", "invalid", "0", "-1", "nan", "inf", "86401"])
def test_forward_mode_rejects_invalid_public_timeout_values(monkeypatch, header_value):
    monkeypatch.setattr(config.settings_finhub_proxy, "proxy_mode", "Forward")
    monkeypatch.setattr(config.settings_finhub_proxy, "url_ai_task_node", "https://proxy.example")

    response = client.post(
        "/ai/analyze_ticker",
        json={"symbol": "NASDAQ:AAPL"},
        headers={"X-FinHub-Forward-Timeout-Seconds": header_value},
    )

    assert response.status_code == 422
    assert response.json()["status"] == 422


class _FailingAsyncClient(_ReflectingAsyncClient):
    async def request(self, method, url, *, content, headers):
        raise httpx2.ConnectError("connection failed")


def test_forwarding_failures_return_public_bad_gateway_response(monkeypatch):
    monkeypatch.setattr(config.settings_finhub_proxy, "proxy_mode", "Forward")
    monkeypatch.setattr(config.settings_finhub_proxy, "url_ai_task_node", "https://proxy.example")
    monkeypatch.setattr(proxy_handler.httpx2, "AsyncClient", _FailingAsyncClient)

    response = client.post("/ai/analyze_ticker", json={"symbol": "NASDAQ:AAPL"})

    assert response.status_code == 502
    assert response.json()["status"] == 502
    assert "data" not in response.json()
