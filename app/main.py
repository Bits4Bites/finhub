from fastapi import FastAPI

# from .config import settings
from .routers import stocks

VERSION = "0.1.0"
APP_NAME = "Hello World API"
APP_DESCRIPTION = "A simple Hello World API server"

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

# Register routers
app.include_router(stocks.router)


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
