import datetime
import traceback
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import version
from .routers import (
    ai,
    ai_dividend,
    ai_portfolio_construction,
    ai_portfolio_review,
    ai_portfolio_spotlight,
    ai_ticker,
    events_div,
    events_earnings,
    events_listings,
    market,
    stocks,
    toz,
)
from .routers import async_task as router_async_task
from .schemas.base_req_resp import BaseResponse
from .utils import auth

APP_NAME = "FinHub API"
APP_DESCRIPTION = "A developer-first financial API hub for stock market data."


class RootResponse(BaseModel):
    """Public welcome response."""

    status: Literal[200] = 200
    message: Literal["Welcome to the FinHub API!"] = "Welcome to the FinHub API!"


class HealthResponse(BaseModel):
    """Public application-liveness response."""

    status: Literal[200] = 200
    message: Literal["ok"] = "ok"


class AppInfo(BaseModel):
    """Application identity and server-local observation time."""

    app_name: str
    app_description: str
    version: str
    server_time: str = Field(
        pattern=r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$",
        description="Server-local wall-clock time at response creation, with second precision.",
    )


class AppInfoResponse(BaseModel):
    """Public application-information response."""

    status: Literal[200] = 200
    message: Literal["ok"] = "ok"
    data: AppInfo


# Initialize API server
openapi_tags_metadata = [
    {
        "name": "root",
        "description": "Root endpoint returning a welcome message.",
    },
    {
        "name": "health",
        "description": "Endpoint for health check.",
    },
    {
        "name": "info",
        "description": "Endpoint for application information.",
    },
]


app = FastAPI(
    openapi_tags=openapi_tags_metadata,
    title=APP_NAME,
    description=APP_DESCRIPTION,
    version=version.VERSION,
    contact={
        "name": "Thanh Nguyen",
        "url": "https://github.com/btnguyen2k/",
        "email": "btnguyen2k [at] gmail(dot)com",
    },
    license_info={
        "name": "MIT",
        "url": "https://github.com/btnguyen2k/qnd-papi-template/blob/main/LICENSE.md",
    },
    swagger_ui_parameters={"syntaxHighlight.theme": "obsidian"},  # Custom theme
)

_AUTH_RESPONSES = {
    401: {
        "model": BaseResponse,
        "description": "The configured API key is missing or invalid.",
        "content": {
            "application/json": {
                "example": {
                    "status": 401,
                    "message": "Invalid or missing API key",
                }
            }
        },
    },
}
_SERVER_ERROR_RESPONSES = {
    500: {
        "model": BaseResponse,
        "description": "An unexpected dependency or server failure occurred.",
    },
}
_VALIDATION_RESPONSES = {
    422: router_async_task.validation_error_response(
        "Request validation failed.",
        BaseResponse,
    ),
}
_PROXY_RESPONSES = {
    307: {
        "description": "The request is redirected temporarily to the configured FinHub node.",
    },
    422: router_async_task.validation_error_response(
        "Request validation failed or the proxy forward-timeout header is invalid.",
        BaseResponse,
    ),
    502: {
        "model": BaseResponse,
        "description": "The configured FinHub node could not be reached in forward mode.",
    },
}


@app.middleware("http")
async def catch_exceptions_middleware(request: Request, call_next):
    """Return a consistent HTTP 500 envelope for unhandled request failures.

    Args:
        request: Incoming HTTP request.
        call_next: The next application handler in the middleware chain.

    Returns:
        The downstream response, or a JSON envelope with HTTP and application
        status 500 when an unhandled exception escapes.

    Notes:
        HTTP exceptions handled by FastAPI use ``http_exception_handler``
        instead. The error message contains the originating exception text.
    """
    try:
        return await call_next(request)
    except Exception as exc:
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"status": 500, "message": f"Error: {exc}"},
        )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Render a FastAPI HTTP exception in the standard FinHub envelope.

    Args:
        request: Request that raised the exception.
        exc: HTTP exception containing the public status, detail, and headers.

    Returns:
        A JSON response preserving the exception status, detail, and headers as
        ``status`` and ``message`` envelope fields.
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={"status": exc.status_code, "message": exc.detail},
        headers=exc.headers,
    )


# Register routers
app.include_router(
    ai.router,
    dependencies=[Depends(auth.verify_api_key)],
    responses={**_AUTH_RESPONSES, **_SERVER_ERROR_RESPONSES},
)
app.include_router(
    ai_dividend.router,
    dependencies=[Depends(auth.verify_api_key)],
    responses={**_AUTH_RESPONSES, **_SERVER_ERROR_RESPONSES, **_PROXY_RESPONSES},
)
app.include_router(
    ai_portfolio_construction.router,
    dependencies=[Depends(auth.verify_api_key)],
    responses={**_AUTH_RESPONSES, **_SERVER_ERROR_RESPONSES, **_PROXY_RESPONSES},
)
app.include_router(
    ai_portfolio_review.router,
    dependencies=[Depends(auth.verify_api_key)],
    responses={**_AUTH_RESPONSES, **_SERVER_ERROR_RESPONSES, **_PROXY_RESPONSES},
)
app.include_router(
    ai_portfolio_spotlight.router,
    dependencies=[Depends(auth.verify_api_key)],
    responses={**_AUTH_RESPONSES, **_SERVER_ERROR_RESPONSES, **_PROXY_RESPONSES},
)
app.include_router(
    ai_ticker.router,
    dependencies=[Depends(auth.verify_api_key)],
    responses={**_AUTH_RESPONSES, **_SERVER_ERROR_RESPONSES, **_PROXY_RESPONSES},
)
app.include_router(
    events_div.router,
    dependencies=[Depends(auth.verify_api_key)],
    responses={**_AUTH_RESPONSES, **_SERVER_ERROR_RESPONSES, **_PROXY_RESPONSES},
)
app.include_router(
    events_earnings.router,
    dependencies=[Depends(auth.verify_api_key)],
    responses={**_AUTH_RESPONSES, **_SERVER_ERROR_RESPONSES, **_PROXY_RESPONSES},
)
app.include_router(
    events_listings.router,
    dependencies=[Depends(auth.verify_api_key)],
    responses={**_AUTH_RESPONSES, **_SERVER_ERROR_RESPONSES, **_PROXY_RESPONSES},
)
app.include_router(
    stocks.router,
    dependencies=[Depends(auth.verify_api_key)],
    responses={**_AUTH_RESPONSES, **_VALIDATION_RESPONSES, **_SERVER_ERROR_RESPONSES},
)
app.include_router(
    toz.router,
    dependencies=[Depends(auth.verify_api_key)],
    responses={**_AUTH_RESPONSES, **_VALIDATION_RESPONSES, **_SERVER_ERROR_RESPONSES},
)
app.include_router(market.router)


@app.get("/", tags=["root"], response_model=RootResponse)
async def root() -> RootResponse:
    """Return the public FinHub welcome response.

    Returns:
        HTTP 200 with exactly ``status=200`` and
        ``message="Welcome to the FinHub API!"``.

    Notes:
        This endpoint is always open, including when API-key authentication is
        configured for protected route prefixes.
    """
    return RootResponse()


@app.get("/health", tags=["health"], response_model=HealthResponse)
async def health() -> HealthResponse:
    """Report that the API process is reachable.

    Returns:
        HTTP 200 with exactly ``{"status": 200, "message": "ok"}``.

    Notes:
        This liveness endpoint is public and does not check downstream market,
        crawler, or AI providers.
    """
    return HealthResponse()


@app.get("/info", tags=["info"], response_model=AppInfoResponse)
async def info() -> AppInfoResponse:
    """Return application identity, version, and observation time.

    Returns:
        HTTP 200 with application name, description, version, and the
        server-local wall-clock time at response creation.

    Notes:
        ``server_time`` uses fixed-width ``YYYY-MM-DD HH:MM:SS`` with second
        precision and no timezone suffix. It is freshly generated for each
        request. This endpoint is public.
    """
    return AppInfoResponse(
        data=AppInfo(
            app_name=APP_NAME,
            app_description=APP_DESCRIPTION,
            version=version.VERSION,
            server_time=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
    )
