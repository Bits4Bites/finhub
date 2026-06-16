import secrets

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from .. import config

# HTTP header names are case-insensitive, so clients may send "X-API-Key",
# "x-api-key", "X-Api-Key", etc. - Starlette resolves them all to this name.
API_KEY_HEADER_NAME = "X-API-Key"

_api_key_header = APIKeyHeader(name=API_KEY_HEADER_NAME, auto_error=False)


async def verify_api_key(api_key: str | None = Security(_api_key_header)) -> None:
    """
    FastAPI dependency that authenticates a request via the X-API-Key header.

    Behaviour:
        - If no API key is configured on the server (config.settings_app.api_key is empty),
          authentication is disabled and all requests are allowed (fail-open).
        - Otherwise, the request must carry an X-API-Key header whose value matches the
          configured key, compared in constant time. A mismatch or missing header raises 401.
    """
    configured_key = config.settings_app.api_key
    if not configured_key:
        # No key configured: authentication disabled (fail-open).
        return

    if not api_key or not secrets.compare_digest(api_key, configured_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
