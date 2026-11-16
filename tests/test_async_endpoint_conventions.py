import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

ASYNC_ENDPOINTS = [
    ("get", "/events/upcoming_dividends"),
    ("get", "/events/upcoming_earnings"),
    ("get", "/events/new_listings"),
    ("post", "/ai/analyze_ticker"),
    ("post", "/ai/build_portfolio"),
    ("post", "/ai/analyze_portfolio"),
    ("post", "/ai/analyze_dividend_event"),
    ("post", "/ai/spotlight_portfolio"),
]
HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "head", "trace"}
PROTECTED_PREFIXES = ("/stocks", "/events", "/ai", "/toz")


def _schema_refs(value):
    if isinstance(value, dict):
        refs = {value["$ref"]} if "$ref" in value else set()
        return refs.union(*(_schema_refs(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(_schema_refs(item) for item in value))
    return set()


@pytest.fixture(scope="module")
def openapi_schema():
    response = client.get("/openapi.json")
    assert response.status_code == 200
    return response.json()


@pytest.mark.parametrize(("method", "sync_path"), ASYNC_ENDPOINTS)
def test_async_endpoint_groups_expose_sync_start_and_poll_operations(openapi_schema, method, sync_path):
    paths = openapi_schema["paths"]
    prefix, feature = sync_path.rsplit("/", maxsplit=1)
    start_path = f"{prefix}/start_{feature}_async"
    poll_path = f"{prefix}/poll_{feature}_async"

    assert method in paths[sync_path]
    assert method in paths[start_path]
    assert method in paths[poll_path]
    assert f"{sync_path}_async" not in paths

    start_operation = paths[start_path][method]
    poll_operation = paths[poll_path][method]
    assert not any(parameter["name"] == "task_id" for parameter in start_operation.get("parameters", []))
    assert any(
        parameter["name"] == "task_id" and parameter["in"] == "query" and parameter["required"] is True
        for parameter in poll_operation.get("parameters", [])
    )
    assert "requestBody" not in poll_operation


@pytest.mark.parametrize(
    "path",
    [
        "/ai/start_analyze_ticker_async",
        "/ai/start_analyze_dividend_event_async",
        "/ai/start_build_portfolio_async",
        "/ai/start_analyze_portfolio_async",
        "/ai/start_spotlight_portfolio_async",
    ],
)
def test_post_async_start_bodies_are_required_and_schema_documented(openapi_schema, path):
    operation = openapi_schema["paths"][path]["post"]
    request_body = operation["requestBody"]

    assert request_body["required"] is True
    assert request_body["content"]["application/json"]["schema"]
    assert "#/components/schemas/BaseResponse" in _schema_refs(
        operation["responses"]["400"]["content"]["application/json"]["schema"]
    )


@pytest.mark.parametrize(
    ("method", "sync_path"),
    ASYNC_ENDPOINTS,
)
def test_async_operations_document_lifecycle_auth_and_proxy_outcomes(openapi_schema, method, sync_path):
    prefix, feature = sync_path.rsplit("/", maxsplit=1)
    paths = [
        f"{prefix}/start_{feature}_async",
        f"{prefix}/poll_{feature}_async",
    ]

    for path in paths:
        responses = openapi_schema["paths"][path][method]["responses"]

        assert {"200", "202", "307", "401", "404", "422", "500", "502"} <= set(responses)
        assert "redirect" in responses["307"]["description"].lower()
        assert "#/components/schemas/BaseResponse" in _schema_refs(
            responses["401"]["content"]["application/json"]["schema"]
        )
        assert {
            "#/components/schemas/HTTPValidationError",
            "#/components/schemas/BaseResponse",
        } <= _schema_refs(responses["422"]["content"]["application/json"]["schema"])
        assert "#/components/schemas/BaseResponse" in _schema_refs(
            responses["500"]["content"]["application/json"]["schema"]
        )
        assert "#/components/schemas/BaseResponse" in _schema_refs(
            responses["502"]["content"]["application/json"]["schema"]
        )


@pytest.mark.parametrize(
    ("method", "path", "application_failure_codes"),
    [
        ("post", "/ai/start_analyze_ticker_async", {"400", "422", "502"}),
        ("post", "/ai/poll_analyze_ticker_async", {"422", "502"}),
        (
            "post",
            "/ai/start_analyze_dividend_event_async",
            {"400", "422", "502"},
        ),
        (
            "post",
            "/ai/poll_analyze_dividend_event_async",
            {"400", "422", "502"},
        ),
        ("post", "/ai/start_build_portfolio_async", {"400", "422", "502"}),
        ("post", "/ai/poll_build_portfolio_async", {"422", "502"}),
        (
            "post",
            "/ai/start_analyze_portfolio_async",
            {"400", "422", "502"},
        ),
        ("post", "/ai/poll_analyze_portfolio_async", {"422", "502"}),
        (
            "post",
            "/ai/start_spotlight_portfolio_async",
            {"400", "422", "502"},
        ),
        ("post", "/ai/poll_spotlight_portfolio_async", {"422", "502"}),
    ],
)
def test_async_ai_operations_document_workflow_failure_outcomes(
    openapi_schema,
    method,
    path,
    application_failure_codes,
):
    responses = openapi_schema["paths"][path][method]["responses"]

    assert application_failure_codes <= set(responses)
    for code in application_failure_codes:
        assert responses[code]["description"]


@pytest.mark.parametrize(("method", "path"), ASYNC_ENDPOINTS)
def test_proxy_capable_sync_operations_document_public_outcomes(openapi_schema, method, path):
    responses = openapi_schema["paths"][path][method]["responses"]

    assert {"200", "307", "401", "422", "500", "502"} <= set(responses)
    assert {
        "#/components/schemas/HTTPValidationError",
        "#/components/schemas/BaseResponse",
    } <= _schema_refs(responses["422"]["content"]["application/json"]["schema"])
    assert "#/components/schemas/BaseResponse" in _schema_refs(
        responses["502"]["content"]["application/json"]["schema"]
    )


def test_stock_and_toz_operations_document_auth_validation_and_server_failures(openapi_schema):
    for path, path_item in openapi_schema["paths"].items():
        if not path.startswith(("/stocks", "/toz")):
            continue
        for method, operation in path_item.items():
            if method not in HTTP_METHODS:
                continue
            responses = operation["responses"]
            assert {"200", "401", "422", "500"} <= set(responses)
            assert "#/components/schemas/BaseResponse" in _schema_refs(
                responses["401"]["content"]["application/json"]["schema"]
            )
            assert {
                "#/components/schemas/HTTPValidationError",
                "#/components/schemas/BaseResponse",
            } <= _schema_refs(responses["422"]["content"]["application/json"]["schema"])
            assert "#/components/schemas/BaseResponse" in _schema_refs(
                responses["500"]["content"]["application/json"]["schema"]
            )


def test_market_index_documents_not_found_without_authentication(openapi_schema):
    operation = openapi_schema["paths"]["/market/index/{index_id}"]["get"]
    responses = operation["responses"]

    assert {"200", "404", "422"} <= set(responses)
    assert "#/components/schemas/BaseResponse" in _schema_refs(
        responses["404"]["content"]["application/json"]["schema"]
    )
    assert "security" not in operation


@pytest.mark.parametrize(
    "path",
    [
        "/ai/analyze_ticker",
        "/ai/analyze_dividend_event",
        "/ai/build_portfolio",
        "/ai/analyze_portfolio",
        "/ai/spotlight_portfolio",
    ],
)
def test_ai_sync_operations_document_both_validation_and_application_422_bodies(openapi_schema, path):
    schema = openapi_schema["paths"][path]["post"]["responses"]["422"]["content"]["application/json"]["schema"]
    refs = _schema_refs(schema)

    assert "#/components/schemas/HTTPValidationError" in refs
    assert "#/components/schemas/BaseResponse" in refs


def test_openapi_security_matches_documented_open_and_protected_routes(openapi_schema):
    for path, path_item in openapi_schema["paths"].items():
        for method, operation in path_item.items():
            if method not in HTTP_METHODS:
                continue
            if path.startswith(PROTECTED_PREFIXES):
                assert operation["security"] == [{"APIKeyHeader": []}]
                assert "401" in operation["responses"]
                auth_content = operation["responses"]["401"]["content"]["application/json"]
                assert "#/components/schemas/BaseResponse" in _schema_refs(auth_content["schema"])
                assert auth_content["example"] == {
                    "status": 401,
                    "message": "Invalid or missing API key",
                }
            else:
                assert "security" not in operation
                assert "401" not in operation["responses"]

    assert openapi_schema["components"]["securitySchemes"]["APIKeyHeader"] == {
        "type": "apiKey",
        "in": "header",
        "name": "X-API-Key",
    }


def test_root_health_and_info_have_explicit_response_schemas(openapi_schema):
    expected_refs = {
        "/": "#/components/schemas/RootResponse",
        "/health": "#/components/schemas/HealthResponse",
        "/info": "#/components/schemas/AppInfoResponse",
    }

    for path, expected_ref in expected_refs.items():
        response_schema = openapi_schema["paths"][path]["get"]["responses"]["200"]["content"]["application/json"][
            "schema"
        ]
        assert response_schema == {"$ref": expected_ref}
