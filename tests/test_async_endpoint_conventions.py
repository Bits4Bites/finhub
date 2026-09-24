import pytest

from app.main import app

_HTTP_METHODS = {"get", "post", "put", "patch", "delete"}
_ASYNC_ENDPOINTS = [
    ("get", "/events/upcoming_dividends"),
    ("get", "/events/upcoming_earnings"),
    ("get", "/events/new_listings"),
    ("post", "/ai/analyze_ticker"),
    ("post", "/ai/build_portfolio"),
    ("post", "/ai/analyze_portfolio"),
    ("post", "/ai/analyze_dividend_event"),
    ("post", "/ai/spotlight_portfolio"),
]


@pytest.mark.parametrize(("method", "sync_path"), _ASYNC_ENDPOINTS)
def test_async_endpoints_split_start_and_poll_with_matching_verbs(method, sync_path):
    paths = app.openapi()["paths"]
    route_prefix, feature = sync_path.rsplit("/", maxsplit=1)
    legacy_path = f"{sync_path}_async"
    start_path = f"{route_prefix}/start_{feature}_async"
    poll_path = f"{route_prefix}/poll_{feature}_async"

    assert set(paths[sync_path]) & _HTTP_METHODS == {method}
    assert set(paths[start_path]) & _HTTP_METHODS == {method}
    assert set(paths[poll_path]) & _HTTP_METHODS == {method}
    assert legacy_path not in paths

    start_parameters = paths[start_path][method].get("parameters", [])
    assert not any(parameter.get("name") == "task_id" for parameter in start_parameters)

    poll_operation = paths[poll_path][method]
    poll_parameters = poll_operation.get("parameters", [])
    assert any(
        parameter.get("name") == "task_id" and parameter.get("in") == "query" and parameter.get("required") is True
        for parameter in poll_parameters
    )
    assert "requestBody" not in poll_operation
