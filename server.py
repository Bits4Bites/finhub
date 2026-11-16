import sys


def resolve_listen_port(raw_value: str | None) -> int:
    """Resolve the server port from an optional environment value.

    Args:
        raw_value: Raw ``LISTEN_PORT`` value, or ``None`` when unset.

    Returns:
        The supplied positive integer, otherwise the default port 8000.
        Missing, blank, malformed, zero, and negative values all use the
        default.
    """
    try:
        listen_port = int(raw_value) if raw_value is not None else 8000
    except TypeError, ValueError:
        return 8000
    return listen_port if listen_port > 0 else 8000


if __name__ == "__main__":
    import os

    listen_port = resolve_listen_port(os.getenv("LISTEN_PORT"))

    reload = os.getenv("RELOAD", "false").lower() == "true"

    import uvicorn

    loop = "none" if sys.platform.startswith("win") else "auto"
    uvicorn.run("app.main:app", host="0.0.0.0", port=listen_port, reload=reload, loop=loop)
