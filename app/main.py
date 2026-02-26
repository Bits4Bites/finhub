import traceback

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .routers import stocks, ai

VERSION = "0.1.3"
APP_NAME = "FinHub API"
APP_DESCRIPTION = "A developer-first financial API hub for stock market data."

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

app = FastAPI(
    openapi_tags=openapi_tags_metadata,
    title=APP_NAME,
    description=APP_DESCRIPTION,
    version=VERSION,
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


# Register routers
app.include_router(stocks.router)
app.include_router(ai.router)


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
