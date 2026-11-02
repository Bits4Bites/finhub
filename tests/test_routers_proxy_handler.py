import asyncio
import gzip
from unittest.mock import AsyncMock, MagicMock, patch

import httpx2
import pytest
from fastapi import HTTPException, Request

from app.routers import proxy_handler


def _request(
    path: str,
    query: str = "",
    *,
    method: str = "GET",
    body: bytes = b"",
    headers: list[tuple[str, str]] | None = None,
) -> Request:
    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": method,
            "scheme": "https",
            "path": path,
            "root_path": "",
            "query_string": query.encode(),
            "headers": [(name.encode(), value.encode()) for name, value in headers or []],
            "client": ("testclient", 50000),
            "server": ("origin.example", 443),
        },
        receive,
    )


def test_handle_if_proxy_preserves_existing_query_and_fragment():
    response = asyncio.run(
        proxy_handler.handle_if_proxy(
            "Redirect",
            "https://proxy.example?source=primary#results",
            _request("/events/listings", "country=AU+%26+NZ"),
        )
    )

    assert response is not None
    assert response.status_code == 307
    assert (
        response.headers["location"] == "https://proxy.example/events/listings?source=primary&country=AU+%26+NZ#results"
    )


def test_handle_if_proxy_omits_question_mark_without_query_parameters():
    response = asyncio.run(
        proxy_handler.handle_if_proxy(
            "Redirect",
            "https://proxy.example",
            _request("/events/listings"),
        )
    )

    assert response is not None
    assert response.headers["location"] == "https://proxy.example/events/listings"


def test_handle_if_proxy_preserves_node_base_path():
    response = asyncio.run(
        proxy_handler.handle_if_proxy(
            "Redirect",
            "https://proxy.example/finhub/",
            _request("/events/listings", "country=AU"),
        )
    )

    assert response is not None
    assert response.headers["location"] == "https://proxy.example/finhub/events/listings?country=AU"


def test_handle_if_proxy_returns_none_when_disabled():
    response = asyncio.run(
        proxy_handler.handle_if_proxy(
            "None",
            "https://proxy.example",
            _request("/events/listings"),
        )
    )

    assert response is None


def test_forward_timeout_uses_600_second_default():
    timeout = proxy_handler._forward_timeout(_request("/events/listings"))

    assert timeout.connect == proxy_handler._FORWARD_CONNECT_TIMEOUT_SECONDS
    assert timeout.read == 600
    assert timeout.write == proxy_handler._FORWARD_WRITE_TIMEOUT_SECONDS
    assert timeout.pool == proxy_handler._FORWARD_POOL_TIMEOUT_SECONDS


def test_forward_timeout_uses_client_header():
    timeout = proxy_handler._forward_timeout(
        _request(
            "/events/listings",
            headers=[("x-finhub-forward-timeout-seconds", "14400")],
        )
    )

    assert timeout.read == 14400


@pytest.mark.parametrize("header_value", ["", "invalid", "0", "-1", "nan", "inf", "86401"])
def test_forward_timeout_rejects_invalid_client_header(header_value):
    with pytest.raises(HTTPException) as exc_info:
        proxy_handler._forward_timeout(
            _request(
                "/events/listings",
                headers=[("x-finhub-forward-timeout-seconds", header_value)],
            )
        )

    assert exc_info.value.status_code == 422


def test_handle_if_proxy_forwards_request_and_upstream_response():
    upstream_response = httpx2.Response(
        status_code=201,
        headers=[
            ("content-type", "application/json"),
            ("content-encoding", "gzip"),
            ("content-length", "999"),
            ("set-cookie", "first=1"),
            ("set-cookie", "second=2"),
            ("connection", "x-upstream"),
            ("x-upstream", "remove"),
            ("x-result", "preserve"),
        ],
        content=gzip.compress(b'{"created":true}'),
    )
    client = AsyncMock()
    client.request.return_value = upstream_response
    client_context = MagicMock()
    client_context.__aenter__ = AsyncMock(return_value=client)
    client_context.__aexit__ = AsyncMock(return_value=None)
    request = _request(
        "/events/listings",
        "country=AU",
        method="POST",
        body=b'{"name":"Example"}',
        headers=[
            ("host", "origin.example"),
            ("content-type", "application/json"),
            ("content-length", "18"),
            ("accept-encoding", "gzip"),
            ("connection", "keep-alive, x-remove"),
            ("x-remove", "remove"),
            ("x-api-key", "secret"),
        ],
    )

    with patch.object(proxy_handler.httpx2, "AsyncClient", return_value=client_context) as client_factory:
        response = asyncio.run(
            proxy_handler.handle_if_proxy(
                "Forward",
                "https://proxy.example/finhub?source=primary",
                request,
            )
        )

    client_factory.assert_called_once()
    client_options = client_factory.call_args.kwargs
    assert client_options["follow_redirects"] is False
    assert client_options["timeout"].read == proxy_handler._FORWARD_DEFAULT_READ_TIMEOUT_SECONDS
    client.request.assert_awaited_once()
    request_args = client.request.await_args
    assert request_args.args == (
        "POST",
        "https://proxy.example/finhub/events/listings?source=primary&country=AU",
    )
    assert request_args.kwargs["content"] == b'{"name":"Example"}'
    forwarded_headers = dict(request_args.kwargs["headers"])
    assert forwarded_headers[b"content-type"] == b"application/json"
    assert forwarded_headers[b"x-api-key"] == b"secret"
    assert forwarded_headers[b"accept-encoding"] == b"identity"
    assert b"host" not in forwarded_headers
    assert b"content-length" not in forwarded_headers
    assert b"connection" not in forwarded_headers
    assert b"x-remove" not in forwarded_headers

    assert response is not None
    assert response.status_code == 201
    assert response.body == b'{"created":true}'
    assert response.headers["content-type"] == "application/json"
    assert response.headers["content-length"] == str(len(response.body))
    assert response.headers["x-result"] == "preserve"
    assert response.headers.getlist("set-cookie") == ["first=1", "second=2"]
    assert "content-encoding" not in response.headers
    assert "connection" not in response.headers
    assert "x-upstream" not in response.headers


def test_handle_if_proxy_maps_forwarding_failure_to_bad_gateway():
    client = AsyncMock()
    client.request.side_effect = httpx2.ConnectError("connection failed")
    client_context = MagicMock()
    client_context.__aenter__ = AsyncMock(return_value=client)
    client_context.__aexit__ = AsyncMock(return_value=None)

    with (
        patch.object(proxy_handler.httpx2, "AsyncClient", return_value=client_context),
        pytest.raises(HTTPException) as exc_info,
    ):
        asyncio.run(
            proxy_handler.handle_if_proxy(
                "Forward",
                "https://proxy.example",
                _request("/events/listings"),
            )
        )

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == "Proxy forwarding failed"
