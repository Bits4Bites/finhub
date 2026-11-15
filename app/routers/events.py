import logging

from fastapi import APIRouter, BackgroundTasks, Query, Request, Response, status

from .. import config
from ..schemas import async_task
from ..schemas import events as schemas_event
from ..services import event as services_event
from ..utils import conv
from . import async_task as router_async_task
from . import proxy_handler

router = APIRouter(prefix="/events", tags=["events"])

_UPCOMING_EARNINGS_TASK_TYPE = "upcoming_earnings"


async def _get_upcoming_earnings_event_result(country: str, index: str) -> schemas_event.UpcomingEarningsResponse:
    country = conv.country_to_iso2(country)
    match country:
        case "AU":
            events = await services_event.get_asx_upcoming_earnings_events(index)
        case "US":
            events = await services_event.get_us_upcoming_earnings_events(index)
        case _:
            return schemas_event.UpcomingEarningsResponse(status=501, message=f"Unsupported country '{country}'")

    return schemas_event.UpcomingEarningsResponse(status=200, message="ok", data=events)


@router.get(
    "/upcoming_earnings", response_model=schemas_event.UpcomingEarningsResponse, response_model_exclude_none=True
)
async def get_upcoming_earnings_event(
    request: Request,
    country: str = Query(description="Country code to filter events by (only 'AU' and 'US' are supported)."),
    index: str = Query(
        "",
        description="Optional stock index to filter events by (support 'ASX20', 'ASX50', 'ASX100', 'ASX200', 'ASX300', 'NASDAQ100', 'SP500', 'SP400', 'SP600').",
    ),
) -> schemas_event.UpcomingEarningsResponse | Response:
    """
    Check for upcoming earnings events for a market.
    """
    proxy_response = await proxy_handler.handle_if_proxy(
        config.settings_finhub_proxy.proxy_mode,
        config.settings_finhub_proxy.url_web_crawl_node,
        request,
    )
    if proxy_response is not None:
        return proxy_response

    return await _get_upcoming_earnings_event_result(country, index)


async def _run_upcoming_earnings_event_task(task_id: str, country: str, index: str) -> None:
    try:
        result = await _get_upcoming_earnings_event_result(country, index)
    except Exception:
        logging.exception("Upcoming earnings task '%s' failed.", task_id)
        await router_async_task.fail_task(task_id, _UPCOMING_EARNINGS_TASK_TYPE)
        return

    await router_async_task.complete_task(
        task_id,
        _UPCOMING_EARNINGS_TASK_TYPE,
        result,
    )


async def _poll_upcoming_earnings_task(
    task_id: str,
    response: Response,
) -> schemas_event.UpcomingEarningsAsyncResponse:
    task_entry = await router_async_task.load_task(task_id, _UPCOMING_EARNINGS_TASK_TYPE)
    task_state = task_entry.state
    task_info = async_task.AsyncTaskInfo(task_id=task_id, state=task_state)
    if task_state == async_task.TASK_STATE_RUNNING:
        response.status_code = status.HTTP_202_ACCEPTED
        return schemas_event.UpcomingEarningsAsyncResponse(
            status=status.HTTP_202_ACCEPTED,
            message="Task is running",
            extra=task_info,
        )
    if task_state == async_task.TASK_STATE_FAILED:
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return schemas_event.UpcomingEarningsAsyncResponse(
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=task_entry.message or "Task failed",
            extra=task_info,
        )

    result = schemas_event.UpcomingEarningsResponse.model_validate(task_entry.result)
    return schemas_event.UpcomingEarningsAsyncResponse(
        status=result.status,
        message=result.message,
        data=result.data,
        extra=task_info,
    )


@router.get(
    "/start_upcoming_earnings_async",
    response_model=schemas_event.UpcomingEarningsAsyncResponse,
    response_model_exclude_none=True,
)
async def start_upcoming_earnings_async(
    background_tasks: BackgroundTasks,
    response: Response,
    request: Request,
    country: str = Query(
        "",
        description="Country code to filter events by.",
    ),
    index: str = Query(
        "",
        description="Optional stock index to filter events by (support 'ASX20', 'ASX50', 'ASX100', 'ASX200', 'ASX300', 'NASDAQ100', 'SP500', 'SP400', 'SP600').",
    ),
) -> schemas_event.UpcomingEarningsAsyncResponse | Response:
    """Start an upcoming-earnings task."""
    proxy_response = await proxy_handler.handle_if_proxy(
        config.settings_finhub_proxy.proxy_mode,
        config.settings_finhub_proxy.url_web_crawl_node,
        request,
    )
    if proxy_response is not None:
        return proxy_response

    task_id, is_new = await router_async_task.start_task(
        _UPCOMING_EARNINGS_TASK_TYPE,
        conv.country_to_iso2(country),
        index.upper(),
    )
    if not is_new:
        return await _poll_upcoming_earnings_task(task_id, response)

    background_tasks.add_task(_run_upcoming_earnings_event_task, task_id, country, index)
    response.status_code = status.HTTP_202_ACCEPTED
    return schemas_event.UpcomingEarningsAsyncResponse(
        status=status.HTTP_202_ACCEPTED,
        message="Task started",
        extra=async_task.AsyncTaskInfo(task_id=task_id, state=async_task.TASK_STATE_RUNNING),
    )


@router.get(
    "/poll_upcoming_earnings_async",
    response_model=schemas_event.UpcomingEarningsAsyncResponse,
    response_model_exclude_none=True,
)
async def poll_upcoming_earnings_async(
    response: Response,
    request: Request,
    task_id: str = Query(description="Task ID returned by the corresponding start endpoint."),
) -> schemas_event.UpcomingEarningsAsyncResponse | Response:
    """Poll an upcoming-earnings task."""
    proxy_response = await proxy_handler.handle_if_proxy(
        config.settings_finhub_proxy.proxy_mode,
        config.settings_finhub_proxy.url_web_crawl_node,
        request,
    )
    if proxy_response is not None:
        return proxy_response

    return await _poll_upcoming_earnings_task(task_id.strip(), response)
