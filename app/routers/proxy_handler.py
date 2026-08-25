import logging
import math
import urllib.parse

import httpx2
from fastapi import HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse

_HOP_BY_HOP_HEADERS = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
)
_FORWARD_REQUEST_EXCLUDED_HEADERS = _HOP_BY_HOP_HEADERS | {"accept-encoding", "content-length", "host"}
_FORWARD_RESPONSE_EXCLUDED_HEADERS = _HOP_BY_HOP_HEADERS | {"content-encoding", "content-length"}
_FORWARD_TIMEOUT_HEADER = "X-FinHub-Forward-Timeout-Seconds"
_FORWARD_CONNECT_TIMEOUT_SECONDS = 10.0
_FORWARD_DEFAULT_READ_TIMEOUT_SECONDS = 600.0
_FORWARD_MAX_READ_TIMEOUT_SECONDS = 86400.0
_FORWARD_WRITE_TIMEOUT_SECONDS = 60.0
_FORWARD_POOL_TIMEOUT_SECONDS = 10.0


def _build_target_url(node_url: str, request: Request) -> str:
    parsed_node_url = urllib.parse.urlsplit(node_url)
    path = f"{parsed_node_url.path.rstrip('/')}/{request.url.path.lstrip('/')}"
    query = "&".join(part for part in (parsed_node_url.query, request.url.query) if part)
    return urllib.parse.urlunsplit(parsed_node_url._replace(path=path, query=query))


def _connection_header_names(connection_header: str | None) -> set[str]:
    if not connection_header:
        return set()
    return {name.strip().lower() for name in connection_header.split(",") if name.strip()}


def _forward_request_headers(request: Request) -> list[tuple[bytes, bytes]]:
    excluded_headers = _FORWARD_REQUEST_EXCLUDED_HEADERS | _connection_header_names(request.headers.get("connection"))
    headers = [
        (name, value) for name, value in request.headers.raw if name.decode("latin-1").lower() not in excluded_headers
    ]
    headers.append((b"accept-encoding", b"identity"))
    return headers


def _forward_response(upstream_response: httpx2.Response) -> Response:
    excluded_headers = _FORWARD_RESPONSE_EXCLUDED_HEADERS | _connection_header_names(
        upstream_response.headers.get("connection")
    )
    response = Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
    )
    for name, value in upstream_response.headers.multi_items():
        if name.lower() not in excluded_headers:
            response.headers.append(name, value)
    return response


def _forward_timeout(request: Request) -> httpx2.Timeout:
    header_value = request.headers.get(_FORWARD_TIMEOUT_HEADER)
    read_timeout = _FORWARD_DEFAULT_READ_TIMEOUT_SECONDS
    if header_value is not None:
        try:
            read_timeout = float(header_value)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"{_FORWARD_TIMEOUT_HEADER} must be a valid number of seconds",
            ) from exc
        if not math.isfinite(read_timeout) or read_timeout <= 0 or read_timeout > _FORWARD_MAX_READ_TIMEOUT_SECONDS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    f"{_FORWARD_TIMEOUT_HEADER} must be greater than 0 and no more than "
                    f"{_FORWARD_MAX_READ_TIMEOUT_SECONDS:g} seconds"
                ),
            )

    return httpx2.Timeout(
        connect=_FORWARD_CONNECT_TIMEOUT_SECONDS,
        read=read_timeout,
        write=_FORWARD_WRITE_TIMEOUT_SECONDS,
        pool=_FORWARD_POOL_TIMEOUT_SECONDS,
    )


async def _forward_request(target_url: str, request: Request) -> Response:
    logging.info("Forwarding request to %s", urllib.parse.quote(target_url, safe=""))
    try:
        async with httpx2.AsyncClient(
            follow_redirects=False,
            timeout=_forward_timeout(request),
        ) as client:
            upstream_response = await client.request(
                request.method,
                target_url,
                content=await request.body(),
                headers=_forward_request_headers(request),
            )
    except httpx2.RequestError as exc:
        logging.exception("Forwarding request failed.")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Proxy forwarding failed",
        ) from exc

    return _forward_response(upstream_response)


async def handle_if_proxy(proxy_mode: str, node_url: str, request: Request, /) -> Response | None:
    if not node_url:
        return None

    target_url = _build_target_url(node_url, request)
    match proxy_mode.upper():
        case "REDIRECT":
            logging.info("Redirecting request to %s", urllib.parse.quote(target_url, safe=""))
            return RedirectResponse(url=target_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
        case "FORWARD":
            return await _forward_request(target_url, request)
        case _:
            return None
