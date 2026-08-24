from fastapi import Request

from app.routers import proxy_handler


def _request(path: str, query: str = "") -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": path,
            "root_path": "",
            "query_string": query.encode(),
            "headers": [],
            "client": ("testclient", 50000),
            "server": ("origin.example", 443),
        }
    )


def test_handle_if_proxy_preserves_existing_query_and_fragment():
    response = proxy_handler.handle_if_proxy(
        "Redirect",
        "https://proxy.example?source=primary#results",
        _request("/events/listings", "country=AU+%26+NZ"),
    )

    assert response is not None
    assert response.status_code == 307
    assert (
        response.headers["location"] == "https://proxy.example/events/listings?source=primary&country=AU+%26+NZ#results"
    )


def test_handle_if_proxy_omits_question_mark_without_query_parameters():
    response = proxy_handler.handle_if_proxy(
        "Redirect",
        "https://proxy.example",
        _request("/events/listings"),
    )

    assert response is not None
    assert response.headers["location"] == "https://proxy.example/events/listings"


def test_handle_if_proxy_preserves_node_base_path():
    response = proxy_handler.handle_if_proxy(
        "Redirect",
        "https://proxy.example/finhub/",
        _request("/events/listings", "country=AU"),
    )

    assert response is not None
    assert response.headers["location"] == "https://proxy.example/finhub/events/listings?country=AU"
