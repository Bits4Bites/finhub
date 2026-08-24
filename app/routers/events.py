import logging
import urllib.parse

from fastapi import APIRouter, BackgroundTasks, Query, Response, status
from fastapi.responses import RedirectResponse

from .. import config
from ..schemas import async_task
from ..schemas import events as schemas_event
from ..services import event as services_event
from ..utils import asset as asset_utils
from ..utils import conv
from . import async_task as router_async_task

router = APIRouter(prefix="/events", tags=["events"])

_UPCOMING_DIVIDENDS_TASK_TYPE = "upcoming_dividends"
_UPCOMING_EARNINGS_TASK_TYPE = "upcoming_earnings"


async def _get_upcoming_dividends_event_result(country: str, index: str) -> schemas_event.UpcomingDividendsResponse:
    country = conv.country_to_iso2(country)
    match country:
        case "AU":
            events = await services_event.get_asx_upcoming_dividends_events(index)
        case "US":
            events = await services_event.get_us_upcoming_dividends_events(index)
        case "VN":
            events = await services_event.get_vn_upcoming_dividends_events(index)
        case _:
            return schemas_event.UpcomingDividendsResponse(status=501, message=f"Unsupported country '{country}'")

    for event in events:
        for major_index in ["ASX300", "NASDAQ100", "SP500", "SP400", "VN100"]:
            if asset_utils.is_in_index(index=major_index, symbol=event.symbol):
                event_date = event.date[:10] if event.date else ""
                logging.info(
                    "Upcoming dividend event: %s (%s) / %s / %s (%.2f%%)",
                    event.symbol,
                    major_index,
                    event_date,
                    event.amount,
                    event.dividend_yield * 100,
                )
                event.analysis = await services_event.analyse_dividend_event(
                    symbol=event.symbol, div_amount=event.amount or 0, ex_date=event_date
                )
                break

    return schemas_event.UpcomingDividendsResponse(status=200, message="ok", data=events)


@router.get(
    "/upcoming_dividends", response_model=schemas_event.UpcomingDividendsResponse, response_model_exclude_none=True
)
async def get_upcoming_dividends_event(
    country: str = Query(description="Country code to filter events by (only 'AU', 'US' and 'VN' are supported)."),
    index: str = Query(
        "",
        description="Optional stock index to filter events by (support 'ASX20', 'ASX50', 'ASX100', 'ASX200', 'ASX300', 'NASDAQ100', 'SP500', 'SP400', 'SP600', 'VN30', 'VN100', 'HNX30').",
    ),
) -> schemas_event.UpcomingDividendsResponse | RedirectResponse:
    """
    Check for upcoming dividend/distribution events for a market.
    """
    if config.settings_finhub_proxy.proxy_mode.upper() == "REDIRECT":
        proxy_url = config.settings_finhub_proxy.url_web_crawl_node.rstrip("/")
        prefix = str(router.prefix)
        e_country = urllib.parse.quote(country, safe="")
        e_index = urllib.parse.quote(index, safe="")
        next_url = f"{proxy_url}{prefix}/upcoming_dividends?country={e_country}&index={e_index}"
        next_url_for_log = urllib.parse.quote(next_url, safe="")
        logging.info(f"Redirecting request to {next_url_for_log}")
        return RedirectResponse(url=next_url, status_code=307)

    return await _get_upcoming_dividends_event_result(country, index)


async def _run_upcoming_dividends_event_task(task_id: str, country: str, index: str) -> None:
    try:
        result = await _get_upcoming_dividends_event_result(country, index)
    except Exception:
        logging.exception("Upcoming dividends task '%s' failed.", task_id)
        await router_async_task.fail_task(task_id, _UPCOMING_DIVIDENDS_TASK_TYPE)
        return

    await router_async_task.complete_task(
        task_id,
        _UPCOMING_DIVIDENDS_TASK_TYPE,
        result,
    )


@router.get(
    "/upcoming_dividends_async",
    response_model=schemas_event.UpcomingDividendsAsyncResponse,
    response_model_exclude_none=True,
)
async def get_upcoming_dividends_event_async(
    background_tasks: BackgroundTasks,
    response: Response,
    country: str = Query(
        "",
        description="Country code to filter events by. Required when starting a task; not required when polling.",
    ),
    index: str = Query(
        "",
        description="Optional stock index to filter events by (support 'ASX20', 'ASX50', 'ASX100', 'ASX200', 'ASX300', 'NASDAQ100', 'SP500', 'SP400', 'SP600', 'VN30', 'VN100', 'HNX30').",
    ),
    task_id: str = Query("", description="Task ID returned by a previous call to this endpoint."),
) -> schemas_event.UpcomingDividendsAsyncResponse | RedirectResponse:
    """
    Start an upcoming-dividends task or poll a previously started task.
    """
    task_id = task_id.strip()
    if config.settings_finhub_proxy.proxy_mode.upper() == "REDIRECT":
        proxy_url = config.settings_finhub_proxy.url_web_crawl_node.rstrip("/")
        prefix = str(router.prefix)
        query = urllib.parse.urlencode({"country": country, "index": index, "task_id": task_id})
        next_url = f"{proxy_url}{prefix}/upcoming_dividends_async?{query}"
        logging.info("Redirecting request to %s", urllib.parse.quote(next_url, safe=""))
        return RedirectResponse(url=next_url, status_code=307)

    if task_id:
        task_entry = await router_async_task.load_task(task_id, _UPCOMING_DIVIDENDS_TASK_TYPE)
        task_state = task_entry.state
        task_info = async_task.AsyncTaskInfo(task_id=task_id, state=task_state)
        if task_state == async_task.TASK_STATE_RUNNING:
            response.status_code = status.HTTP_202_ACCEPTED
            return schemas_event.UpcomingDividendsAsyncResponse(
                status=status.HTTP_202_ACCEPTED,
                message="Task is running",
                extra=task_info,
            )
        if task_state == async_task.TASK_STATE_FAILED:
            response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
            return schemas_event.UpcomingDividendsAsyncResponse(
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
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

    task_id, is_new = await router_async_task.start_task(
        _UPCOMING_DIVIDENDS_TASK_TYPE,
        conv.country_to_iso2(country),
        index.upper(),
    )
    if not is_new:
        return await get_upcoming_dividends_event_async(
            background_tasks=background_tasks,
            response=response,
            country=country,
            index=index,
            task_id=task_id,
        )

    background_tasks.add_task(_run_upcoming_dividends_event_task, task_id, country, index)
    response.status_code = status.HTTP_202_ACCEPTED
    return schemas_event.UpcomingDividendsAsyncResponse(
        status=status.HTTP_202_ACCEPTED,
        message="Task started",
        extra=async_task.AsyncTaskInfo(task_id=task_id, state=async_task.TASK_STATE_RUNNING),
    )


# ----------------------------------------------------------------------


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
    country: str = Query(description="Country code to filter events by (only 'AU' and 'US' are supported)."),
    index: str = Query(
        "",
        description="Optional stock index to filter events by (support 'ASX20', 'ASX50', 'ASX100', 'ASX200', 'ASX300', 'NASDAQ100', 'SP500', 'SP400', 'SP600').",
    ),
) -> schemas_event.UpcomingEarningsResponse | RedirectResponse:
    """
    Check for upcoming earnings events for a market.
    """
    if config.settings_finhub_proxy.proxy_mode.upper() == "REDIRECT":
        proxy_url = config.settings_finhub_proxy.url_web_crawl_node.rstrip("/")
        prefix = str(router.prefix)
        e_country = urllib.parse.quote(country, safe="")
        e_index = urllib.parse.quote(index, safe="")
        next_url = f"{proxy_url}{prefix}/upcoming_earnings?country={e_country}&index={e_index}"
        next_url_for_log = urllib.parse.quote(next_url, safe="")
        logging.info(f"Redirecting request to {next_url_for_log}")
        return RedirectResponse(url=next_url, status_code=307)

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


@router.get(
    "/upcoming_earnings_async",
    response_model=schemas_event.UpcomingEarningsAsyncResponse,
    response_model_exclude_none=True,
)
async def get_upcoming_earnings_event_async(
    background_tasks: BackgroundTasks,
    response: Response,
    country: str = Query(
        "",
        description="Country code to filter events by. Required when starting a task; not required when polling.",
    ),
    index: str = Query(
        "",
        description="Optional stock index to filter events by (support 'ASX20', 'ASX50', 'ASX100', 'ASX200', 'ASX300', 'NASDAQ100', 'SP500', 'SP400', 'SP600').",
    ),
    task_id: str = Query("", description="Task ID returned by a previous call to this endpoint."),
) -> schemas_event.UpcomingEarningsAsyncResponse | RedirectResponse:
    """
    Start an upcoming-earnings task or poll a previously started task.
    """
    task_id = task_id.strip()
    if config.settings_finhub_proxy.proxy_mode.upper() == "REDIRECT":
        proxy_url = config.settings_finhub_proxy.url_web_crawl_node.rstrip("/")
        prefix = str(router.prefix)
        query = urllib.parse.urlencode({"country": country, "index": index, "task_id": task_id})
        next_url = f"{proxy_url}{prefix}/upcoming_earnings_async?{query}"
        logging.info("Redirecting request to %s", urllib.parse.quote(next_url, safe=""))
        return RedirectResponse(url=next_url, status_code=307)

    if task_id:
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

    task_id, is_new = await router_async_task.start_task(
        _UPCOMING_EARNINGS_TASK_TYPE,
        conv.country_to_iso2(country),
        index.upper(),
    )
    if not is_new:
        return await get_upcoming_earnings_event_async(
            background_tasks=background_tasks,
            response=response,
            country=country,
            index=index,
            task_id=task_id,
        )

    background_tasks.add_task(_run_upcoming_earnings_event_task, task_id, country, index)
    response.status_code = status.HTTP_202_ACCEPTED
    return schemas_event.UpcomingEarningsAsyncResponse(
        status=status.HTTP_202_ACCEPTED,
        message="Task started",
        extra=async_task.AsyncTaskInfo(task_id=task_id, state=async_task.TASK_STATE_RUNNING),
    )
