import logging
import random
import traceback
from contextlib import asynccontextmanager

import requests
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from . import config
from .routers import ai, events, stocks, toz
from .utils import auth
from .utils import scheduler as scheduler_utils

VERSION = "0.13.1"
APP_NAME = "FinHub API"
APP_DESCRIPTION = "A developer-first financial API hub for stock market data."

logger = logging.getLogger(__name__)
scheduler = scheduler_utils.BackgroundScheduler()


async def _load_proxies_task() -> None:
    """
    Fetch a fresh proxy list and store a random subset in settings_finhub_proxy.http_proxies.

    On any error the existing http_proxies content is left unchanged.
    """
    _PROXY_LIST_URL = (
        "https://freeproxydb.com/api/proxy/search"
        "?country=US,AU,VN,DE,SG&protocol=http&link_type=http&anonymity=&speed=0,8&https=1&page_index=1&page_size=100"
    )
    _PROXY_SAMPLE_SIZE = 10
    try:
        response = requests.get(_PROXY_LIST_URL, timeout=30)
        response.raise_for_status()
        raw_entries = response.json().get("data", {}).get("data", []) or []

        proxies = [config.HttpProxy.model_validate(entry) for entry in raw_entries]
        if not proxies:
            logger.warning("Proxy list fetch returned no entries; keeping existing http_proxies.")
            return

        sample_size = min(_PROXY_SAMPLE_SIZE, len(proxies))
        config.settings_finhub_proxy.http_proxies = random.sample(proxies, sample_size)
        logger.info("Loaded %d proxies into http_proxies.", sample_size)
        for proxy in config.settings_finhub_proxy.http_proxies:
            logger.info(
                "Loaded proxy: %s:%d (anonymity=%s, speed=%.2f)", proxy.ip, proxy.port, proxy.anonymity, proxy.speed
            )
    except Exception as exc:
        logger.error("Failed to load proxy list: %s", exc)


# Register periodic tasks
if config.settings_finhub_proxy.fetch_website_via_proxy:
    scheduler.register(
        scheduler_utils.PeriodicTask(
            name="load_proxy_list",
            func=_load_proxies_task,
            interval_seconds=3600,
            run_on_start=True,
        )
    )
else:
    logger.info("Proxy fetching is disabled by config; skipping registration of load_proxy_list task.")

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
]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await scheduler.start()
    yield
    await scheduler.stop()


app = FastAPI(
    openapi_tags=openapi_tags_metadata,
    title=APP_NAME,
    description=APP_DESCRIPTION,
    version=VERSION,
    lifespan=lifespan,
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


@app.middleware("http")
async def catch_exceptions_middleware(request: Request, call_next):
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
    return JSONResponse(
        status_code=exc.status_code,
        content={"status": exc.status_code, "message": exc.detail},
        headers=exc.headers,
    )


# Register routers
app.include_router(ai.router, dependencies=[Depends(auth.verify_api_key)])
app.include_router(events.router, dependencies=[Depends(auth.verify_api_key)])
app.include_router(stocks.router, dependencies=[Depends(auth.verify_api_key)])
app.include_router(toz.router, dependencies=[Depends(auth.verify_api_key)])


@app.get("/", tags=["root"])
async def root():
    """
    root endpoint returning a welcome message.
    """
    return {"status": 200, "message": f"Welcome to the {APP_NAME}!"}


@app.get("/health", tags=["health"])
async def health():
    """
    health is the health check endpoint.
    """
    return {"status": 200, "message": "ok"}
