import secrets

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from .. import config

# HTTP header names are case-insensitive, so clients may send "X-API-Key",
# "x-api-key", "X-Api-Key", etc. - Starlette resolves them all to this name.
API_KEY_HEADER_NAME = "X-API-Key"

_api_key_header = APIKeyHeader(name=API_KEY_HEADER_NAME, auto_error=False)


async def verify_api_key(api_key: str | None = Security(_api_key_header)) -> None:
    """Authorize an API request using the configured application key.

    Args:
        api_key: The value supplied in the ``X-API-Key`` request header, or
            ``None`` when the header is absent.

    Returns:
        None when authentication is disabled or the supplied key is valid.

    Raises:
        HTTPException: With status 401 when authentication is enabled and the
            supplied key is missing or invalid. The application exposes this as
            ``{"status": 401, "message": "Invalid or missing API key"}``.

    Notes:
        An empty server-side API key disables authentication. HTTP header names
        are case-insensitive.
    """
    configured_key = config.settings_app.api_key
    if not configured_key:
        # No key configured: authentication disabled (fail-open).
        return

    if not api_key or not secrets.compare_digest(api_key.encode("utf-8"), configured_key.encode("utf-8")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
