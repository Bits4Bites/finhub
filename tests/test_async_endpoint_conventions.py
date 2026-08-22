import pytest

from app.main import app

_HTTP_METHODS = {"get", "post", "put", "patch", "delete"}
_AI_ENDPOINTS = [
    ("get", "/events/new_listings"),
    ("post", "/ai/analyze_ticker"),
    ("post", "/ai/build_portfolio"),
    ("post", "/ai/analyze_portfolio"),
    ("post", "/ai/analyze_dividend_event"),
    ("post", "/ai/spotlight_portfolio"),
]


@pytest.mark.parametrize(("method", "sync_path"), _AI_ENDPOINTS)
def test_ai_async_endpoint_reuses_sync_verb_and_polls_by_query(method, sync_path):
    paths = app.openapi()["paths"]
    async_path = f"{sync_path}_async"

    assert set(paths[sync_path]) & _HTTP_METHODS == {method}
    assert set(paths[async_path]) & _HTTP_METHODS == {method}
    assert f"{async_path}/{{task_id}}" not in paths

    parameters = paths[async_path][method].get("parameters", [])
    assert any(parameter.get("name") == "task_id" and parameter.get("in") == "query" for parameter in parameters)
