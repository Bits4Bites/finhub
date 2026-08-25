import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, Response, status

from .. import config
from ..schemas import async_task
from ..schemas import events_listings as schemas_events_listings
from ..services import msai_asx_listings as services_asx_listings
from ..utils import conv
from . import async_task as router_async_task
from . import proxy_handler

router = APIRouter(prefix="/events", tags=["events"])

_NEW_LISTINGS_TASK_TYPE = "new_listings"


async def _get_new_listings_result(country: str) -> schemas_events_listings.ListingsResponse:
    country = conv.country_to_iso2(country)
    match country:
        case "AU":
            events = await services_asx_listings.ai_get_asx_new_listings()
        case _:
            return schemas_events_listings.ListingsResponse(
                status=501,
                message=f"Unsupported country '{country}'",
            )

    return schemas_events_listings.ListingsResponse(status=200, message="ok", data=events)


@router.get(
    "/new_listings",
    response_model=schemas_events_listings.ListingsResponse,
    response_model_exclude_none=True,
)
async def get_new_listings(
    request: Request,
    country: str = Query("", description="Country code to filter events by (only 'AU' is supported)."),
) -> schemas_events_listings.ListingsResponse | Response:
    """
    Check for new listing events for a market, using AI assistance.
    Note: currently only AU is supported.
    """
    proxy_response = await proxy_handler.handle_if_proxy(
        config.settings_finhub_proxy.proxy_mode,
        config.settings_finhub_proxy.url_ai_task_node,
        request,
    )
    if proxy_response is not None:
        return proxy_response

    return await _get_new_listings_result(country)


async def _run_new_listings_task(task_id: str, country: str) -> None:
    try:
        result = await _get_new_listings_result(country)
    except Exception:
        logging.exception("New listings task '%s' failed.", task_id)
        await router_async_task.fail_task(task_id, _NEW_LISTINGS_TASK_TYPE)
        return

    await router_async_task.complete_task(
        task_id,
        _NEW_LISTINGS_TASK_TYPE,
        result,
    )


@router.get(
    "/new_listings_async",
    response_model=schemas_events_listings.ListingsAsyncResponse,
    response_model_exclude_none=True,
)
async def get_new_listings_async(
    background_tasks: BackgroundTasks,
    request: Request,
    response: Response,
    country: str = Query(
        "",
        description="Country code used when starting a task. Required when starting; only 'AU' is supported.",
    ),
    task_id: str = Query("", description="Task ID returned by a previous call to this endpoint."),
) -> schemas_events_listings.ListingsAsyncResponse | Response:
    """
    Start a new-listings task or poll a previously started task.
    """
    proxy_response = await proxy_handler.handle_if_proxy(
        config.settings_finhub_proxy.proxy_mode,
        config.settings_finhub_proxy.url_ai_task_node,
        request,
    )
    if proxy_response is not None:
        return proxy_response

    task_id = task_id.strip()
    if task_id:
        task_entry = await router_async_task.load_task(task_id, _NEW_LISTINGS_TASK_TYPE)
        task_state = task_entry.state
        task_info = async_task.AsyncTaskInfo(task_id=task_id, state=task_state)
        if task_state == async_task.TASK_STATE_RUNNING:
            response.status_code = status.HTTP_202_ACCEPTED
            return schemas_events_listings.ListingsAsyncResponse(
                status=status.HTTP_202_ACCEPTED,
                message="Task is running",
                extra=task_info,
            )
        if task_state == async_task.TASK_STATE_FAILED:
            response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
            return schemas_events_listings.ListingsAsyncResponse(
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                message=task_entry.message or "Task failed",
                extra=task_info,
            )

        result = schemas_events_listings.ListingsResponse.model_validate(task_entry.result)
        return schemas_events_listings.ListingsAsyncResponse(
            status=result.status,
            message=result.message,
            data=result.data,
            extra=task_info,
        )

    country = conv.country_to_iso2(country)
    if country != "AU":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="New listings supports only country 'AU'",
        )

    task_id, is_new = await router_async_task.start_task(_NEW_LISTINGS_TASK_TYPE, country)
    if not is_new:
        return await get_new_listings_async(
            background_tasks=background_tasks,
            request=request,
            response=response,
            country=country,
            task_id=task_id,
        )

    background_tasks.add_task(_run_new_listings_task, task_id, country)
    response.status_code = status.HTTP_202_ACCEPTED
    return schemas_events_listings.ListingsAsyncResponse(
        status=status.HTTP_202_ACCEPTED,
        message="Task started",
        extra=async_task.AsyncTaskInfo(
            task_id=task_id,
            state=async_task.TASK_STATE_RUNNING,
        ),
    )
