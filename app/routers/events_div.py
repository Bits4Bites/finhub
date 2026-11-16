import logging

import fastapi

from .. import config
from ..schemas import async_task
from ..schemas import events as schemas_event
from ..schemas.base_req_resp import BaseResponse
from ..services import events_div as services_events_div
from ..utils import asset as asset_utils
from ..utils import conv
from . import async_task as router_async_task
from . import proxy_handler

router = fastapi.APIRouter(prefix="/events", tags=["events"])

_UPCOMING_DIVIDENDS_TASK_TYPE = "upcoming_dividends"
_ASYNC_RESPONSES = {
    202: {
        "model": schemas_event.UpcomingDividendsAsyncResponse,
        "description": "The upcoming-dividends task started or is still running.",
    },
    404: {"model": BaseResponse, "description": "The task was not found or has expired."},
    500: {
        "model": schemas_event.UpcomingDividendsAsyncResponse | BaseResponse,
        "description": "The background request or retained task state failed.",
    },
}


async def _get_upcoming_dividends_event_result(country: str, index: str) -> schemas_event.UpcomingDividendsResponse:
    country = conv.country_to_iso2(country)
    match country:
        case "AU":
            events = await services_events_div.get_asx_upcoming_dividends_events(index)
        case "US":
            events = await services_events_div.get_us_upcoming_dividends_events(index)
        case "VN":
            events = await services_events_div.get_vn_upcoming_dividends_events(index)
        case _:
            return schemas_event.UpcomingDividendsResponse(status=501, message=f"Unsupported country '{country}'")

    for event in events:
        for major_index in ["ASX300", "NASDAQ100", "SP500", "SP400", "VN100"]:
            if asset_utils.is_in_index(index=major_index, symbol=event.symbol):
                event_date = event.timestamp_str[:10] if event.timestamp_str else ""
                logging.info(
                    "Upcoming dividend event: %s (%s) / %s / %s (%.2f%%)",
                    event.symbol,
                    major_index,
                    event_date,
                    event.amount,
                    event.dividend_yield * 100,
                )
                event.analysis = await services_events_div.analyse_dividend_event(
                    symbol=event.symbol, div_amount=event.amount or 0, ex_date=event_date
                )
                break

    return schemas_event.UpcomingDividendsResponse(status=200, message="ok", data=events)


@router.get(
    "/upcoming_dividends", response_model=schemas_event.UpcomingDividendsResponse, response_model_exclude_none=True
)
async def get_upcoming_dividends_event(
    request: fastapi.Request,
    country: str = fastapi.Query(
        description="Country code to filter events by (only 'AU', 'US' and 'VN' are supported)."
    ),
    index: str = fastapi.Query(
        "",
        description="Optional stock index to filter events by (support 'ASX20', 'ASX50', 'ASX100', 'ASX200', 'ASX300', 'NASDAQ100', 'SP500', 'SP400', 'SP600', 'VN30', 'VN100', 'HNX30').",
    ),
) -> schemas_event.UpcomingDividendsResponse | fastapi.Response:
    """Return upcoming dividend or distribution events for a supported market.

    Args:
        request: Incoming request used when the endpoint is configured to proxy
            web-crawl traffic.
        country: Australia, the United States, or Vietnam as an ISO alpha-2/
            alpha-3 code, country name, or recognized alias. Matching trims
            whitespace and is case-insensitive; examples include ``AU``/``AUS``/
            ``Australia``, ``US``/``USA``/``United States``, and ``VN``/``VNM``/
            ``Vietnam``.
        index: Optional, case-insensitive market-index filter. Australia supports
            ``ASX20``, ``ASX50``, ``ASX100``, ``ASX200``, and ``ASX300``; the
            United States supports ``NASDAQ100``, ``SP500``, ``SP400``, and
            ``SP600``; Vietnam supports ``VN30``, ``VN100``, and ``HNX30``.
            Unsupported or cross-market indices return an empty list.

    Returns:
        A proxy response when proxying is enabled. Otherwise, a successful
        envelope has status 200 and the service-ordered event list, which may be
        empty. An unsupported country returns HTTP 200 with envelope status 501
        and no data.

    Notes:
        ``country`` is required, so omission returns HTTP 422. Events belonging
        to ``ASX300``, ``NASDAQ100``, ``SP500``, ``SP400``, or ``VN100`` are
        enriched with dividend analysis when analysis is available; a nullable
        analysis result is omitted. Other nullable fields are also omitted.
        Retrieval or enrichment failures are exposed as HTTP 500 responses.
    """
    proxy_response = await proxy_handler.handle_if_proxy(
        config.settings_finhub_proxy.proxy_mode,
        config.settings_finhub_proxy.url_web_crawl_node,
        request,
    )
    if proxy_response is not None:
        return proxy_response

    return await _get_upcoming_dividends_event_result(country, index)


async def _run_upcoming_dividends_event_task(task_id: str, country: str, index: str) -> None:
    try:
        result = await _get_upcoming_dividends_event_result(country, index)
    except Exception:
        logging.exception("Upcoming dividends task '%s' failed.", task_id)
        await router_async_task.task_store.fail(task_id, _UPCOMING_DIVIDENDS_TASK_TYPE)
        return

    await router_async_task.task_store.complete(
        task_id,
        _UPCOMING_DIVIDENDS_TASK_TYPE,
        result,
    )


async def _poll_upcoming_dividends_task(
    task_id: str,
    response: fastapi.Response,
) -> schemas_event.UpcomingDividendsAsyncResponse:
    task_entry = await router_async_task.task_store.load(task_id, _UPCOMING_DIVIDENDS_TASK_TYPE)
    task_state = task_entry.state
    task_info = async_task.AsyncTaskInfo(task_id=task_id, state=task_state)
    if task_state == async_task.TASK_STATE_RUNNING:
        response.status_code = fastapi.status.HTTP_202_ACCEPTED
        return schemas_event.UpcomingDividendsAsyncResponse(
            status=fastapi.status.HTTP_202_ACCEPTED,
            message="Task is running",
            extra=task_info,
        )
    if task_state == async_task.TASK_STATE_FAILED:
        response.status_code = fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR
        return schemas_event.UpcomingDividendsAsyncResponse(
            status=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=task_entry.message or "Task failed",
            extra=task_info,
        )

    result = schemas_event.UpcomingDividendsResponse.model_validate(task_entry.result)
    return schemas_event.UpcomingDividendsAsyncResponse(
        status=result.status,
        message=result.message,
        data=result.data,
        extra=task_info,
    )


@router.get(
    "/start_upcoming_dividends_async",
    response_model=schemas_event.UpcomingDividendsAsyncResponse,
    response_model_exclude_none=True,
    responses=_ASYNC_RESPONSES,
)
async def start_upcoming_dividends_async(
    background_tasks: fastapi.BackgroundTasks,
    response: fastapi.Response,
    request: fastapi.Request,
    country: str = fastapi.Query(
        "",
        description="Country code to filter events by.",
    ),
    index: str = fastapi.Query(
        "",
        description="Optional stock index to filter events by (support 'ASX20', 'ASX50', 'ASX100', 'ASX200', 'ASX300', 'NASDAQ100', 'SP500', 'SP400', 'SP600', 'VN30', 'VN100', 'HNX30').",
    ),
) -> schemas_event.UpcomingDividendsAsyncResponse | fastapi.Response:
    """Start or reuse a background upcoming-dividends request.

    Args:
        background_tasks: FastAPI scheduler used to run a newly created request
            after the start response is prepared.
        response: Response whose HTTP status reflects the returned task state.
        request: Incoming request used when the endpoint is configured to proxy
            web-crawl traffic.
        country: Optional Australia, United States, or Vietnam identifier. ISO
            codes, country names, aliases, whitespace, and case are normalized
            as for the synchronous endpoint. Missing and unsupported values may
            start and later complete with an unsupported-country result.
        index: Optional market-index filter. Matching is case-insensitive and the
            supported values are the same as for the synchronous endpoint.

    Returns:
        A proxy response when proxying is enabled. A new task returns HTTP 202
        with a ``RUNNING`` task descriptor. A duplicate request reuses the task
        for the normalized country and uppercased index and returns its current
        running, completed, or failed outcome.

    Notes:
        Task state and results expire after one hour. Retrieval or enrichment
        failures produce a terminal ``FAILED`` task whose poll response is HTTP
        500. Missing or unsupported countries instead produce a ``COMPLETED``
        task whose poll response is HTTP 200 with envelope status 501.
    """
    proxy_response = await proxy_handler.handle_if_proxy(
        config.settings_finhub_proxy.proxy_mode,
        config.settings_finhub_proxy.url_web_crawl_node,
        request,
    )
    if proxy_response is not None:
        return proxy_response

    task_id, is_new = await router_async_task.task_store.start(
        _UPCOMING_DIVIDENDS_TASK_TYPE,
        conv.country_to_iso2(country),
        index.upper(),
    )
    if not is_new:
        return await _poll_upcoming_dividends_task(task_id, response)

    background_tasks.add_task(_run_upcoming_dividends_event_task, task_id, country, index)
    response.status_code = fastapi.status.HTTP_202_ACCEPTED
    return schemas_event.UpcomingDividendsAsyncResponse(
        status=fastapi.status.HTTP_202_ACCEPTED,
        message="Task started",
        extra=async_task.AsyncTaskInfo(task_id=task_id, state=async_task.TASK_STATE_RUNNING),
    )


@router.get(
    "/poll_upcoming_dividends_async",
    response_model=schemas_event.UpcomingDividendsAsyncResponse,
    response_model_exclude_none=True,
    responses=_ASYNC_RESPONSES,
)
async def poll_upcoming_dividends_async(
    response: fastapi.Response,
    request: fastapi.Request,
    task_id: str = fastapi.Query(description="Task ID returned by the corresponding start endpoint."),
) -> schemas_event.UpcomingDividendsAsyncResponse | fastapi.Response:
    """Return the public state or result of an upcoming-dividends task.

    Args:
        response: Response whose HTTP status is set from the task lifecycle.
        request: Incoming request used when the endpoint is configured to proxy
            web-crawl traffic.
        task_id: Identifier returned by the start endpoint. Surrounding
            whitespace is ignored.

    Returns:
        A proxy response when proxying is enabled. A running task returns HTTP
        202; a failed task returns HTTP 500; and a completed task returns HTTP
        200 with its original envelope status and data. Consequently, an
        unsupported-country completion has HTTP 200 and envelope status 501.

    Notes:
        Unknown, expired, or wrong-type task identifiers return HTTP 404. A
        corrupt stored task returns HTTP 500. Successful event data preserves
        service order, includes available major-index analysis, and omits
        nullable fields.
    """
    proxy_response = await proxy_handler.handle_if_proxy(
        config.settings_finhub_proxy.proxy_mode,
        config.settings_finhub_proxy.url_web_crawl_node,
        request,
    )
    if proxy_response is not None:
        return proxy_response

    return await _poll_upcoming_dividends_task(task_id.strip(), response)
