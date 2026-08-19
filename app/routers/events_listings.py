import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Response, status
from fastapi.responses import RedirectResponse

from ..schemas import async_task
from ..schemas import events as schemas_events
from ..schemas import events_listings as schemas_events_listings
from ..services import msai_asx_listings as services_asx_listings
from ..utils import cache, conv

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
    country: str = Query("", description="Country code to filter events by (only 'AU' is supported)."),
) -> schemas_events_listings.ListingsResponse | RedirectResponse:
    """
    Check for new listing events for a market, using AI assistance.
    Note: currently only AU is supported.
    """
    return await _get_new_listings_result(country)


async def _run_new_listings_task(task_id: str, country: str) -> None:
    try:
        result = await _get_new_listings_result(country)
    except Exception:
        logging.exception("New listings task '%s' failed.", task_id)
        await cache.set(
            task_id,
            {
                "task_type": _NEW_LISTINGS_TASK_TYPE,
                "state": async_task.TASK_STATE_FAILED,
                "message": "Task failed",
            },
            ttl=async_task.ASYNC_TASK_TTL,
        )
        return

    await cache.set(
        task_id,
        {
            "task_type": _NEW_LISTINGS_TASK_TYPE,
            "state": async_task.TASK_STATE_COMPLETED,
            "result": result.model_dump(mode="json"),
        },
        ttl=async_task.ASYNC_TASK_TTL,
    )


@router.get(
    "/new_listings_async",
    response_model=schemas_events_listings.ListingsAsyncResponse,
    response_model_exclude_none=True,
)
async def get_new_listings_async(
    background_tasks: BackgroundTasks,
    response: Response,
    country: str = Query("", description="Country code to filter events by (only 'AU' is supported)."),
    task_id: str = Query("", description="Task ID returned by a previous call to this endpoint."),
) -> schemas_events_listings.ListingsAsyncResponse:
    """
    Start a new-listings task or poll a previously started task.
    """
    task_id = task_id.strip()
    if task_id:
        task_entry = await cache.get(task_id)
        if not isinstance(task_entry, dict) or task_entry.get("task_type") != _NEW_LISTINGS_TASK_TYPE:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

        task_state = task_entry.get("state")
        if task_state not in {
            async_task.TASK_STATE_RUNNING,
            async_task.TASK_STATE_COMPLETED,
            async_task.TASK_STATE_FAILED,
        }:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Invalid task state")

        task_info = schemas_events.AsyncTaskInfo(task_id=task_id, state=task_state)
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
                message=task_entry.get("message", "Task failed"),
                extra=task_info,
            )
        if not isinstance(task_entry.get("result"), dict):
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Invalid task state")

        result = schemas_events_listings.ListingsResponse.model_validate(task_entry["result"])
        return schemas_events_listings.ListingsAsyncResponse(
            status=result.status,
            message=result.message,
            data=result.data,
            extra=task_info,
        )

    task_id = str(uuid.uuid4())
    await cache.set(
        task_id,
        {
            "task_type": _NEW_LISTINGS_TASK_TYPE,
            "state": async_task.TASK_STATE_RUNNING,
        },
        ttl=async_task.ASYNC_TASK_TTL,
    )
    background_tasks.add_task(_run_new_listings_task, task_id, country)
    response.status_code = status.HTTP_202_ACCEPTED
    return schemas_events_listings.ListingsAsyncResponse(
        status=status.HTTP_202_ACCEPTED,
        message="Task started",
        extra=schemas_events.AsyncTaskInfo(
            task_id=task_id,
            state=async_task.TASK_STATE_RUNNING,
        ),
    )
