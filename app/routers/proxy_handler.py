import logging
import urllib.parse

from fastapi import Request
from fastapi.responses import RedirectResponse


def handle_if_proxy(proxy_mode: str, node_url: str, request: Request, /) -> RedirectResponse | None:
    if node_url and proxy_mode.upper() == "REDIRECT":
        parsed_node_url = urllib.parse.urlsplit(node_url)
        path = f"{parsed_node_url.path.rstrip('/')}/{request.url.path.lstrip('/')}"
        query = "&".join(part for part in (parsed_node_url.query, request.url.query) if part)
        next_url = urllib.parse.urlunsplit(parsed_node_url._replace(path=path, query=query))
        next_url_for_log = urllib.parse.quote(next_url, safe="")
        logging.info(f"Redirecting request to {next_url_for_log}")
        return RedirectResponse(url=str(next_url), status_code=307)

    return None
