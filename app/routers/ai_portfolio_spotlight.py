import logging

from fastapi import APIRouter, BackgroundTasks, Body, HTTPException, Query, Response, status

from ..schemas import ai_portfolio_spotlight as schemas_spotlight
from ..schemas import async_task
from ..services import msai_spotlight_portfolio as services_spotlight
from ..services import portfolio_verification
from . import async_task as router_async_task

router = APIRouter(prefix="/ai", tags=["ai"])

_TASK_TYPE = "spotlight_portfolio"


async def _analyze(
    request: schemas_spotlight.PortfolioSpotlightRequest,
) -> schemas_spotlight.PortfolioSpotlightResponse:
    try:
        result = await services_spotlight.ai_spotlight_portfolio(
            portfolio=request.current_allocation,
            country=request.country,
            investor_theme=request.investor_theme,
        )
    except portfolio_verification.PortfolioInputError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except portfolio_verification.PortfolioVerificationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except services_spotlight.PortfolioSpotlightAIError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    return schemas_spotlight.PortfolioSpotlightResponse(
        status=status.HTTP_200_OK,
        message="ok",
        data=result,
    )


@router.post(
    "/spotlight_portfolio",
    response_model=schemas_spotlight.PortfolioSpotlightResponse,
    response_model_exclude_none=True,
)
async def spotlight_portfolio(
    request: schemas_spotlight.PortfolioSpotlightRequest,
) -> schemas_spotlight.PortfolioSpotlightResponse:
    """Review a verified portfolio and return ranked structured risks and actions."""

    return await _analyze(request)


async def _run_task(
    task_id: str,
    request: schemas_spotlight.PortfolioSpotlightRequest,
) -> None:
    try:
        result = await _analyze(request)
    except HTTPException as exc:
        await router_async_task.fail_task(
            task_id,
            _TASK_TYPE,
            status_code=exc.status_code,
            message=str(exc.detail),
        )
        return
    except Exception:
        logging.exception("Spotlight portfolio task '%s' failed.", task_id)
        await router_async_task.fail_task(
            task_id,
            _TASK_TYPE,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
        return

    await router_async_task.complete_task(
        task_id,
        _TASK_TYPE,
        result,
        status_code=result.status,
        message=result.message,
    )


@router.post(
    "/spotlight_portfolio_async",
    response_model=schemas_spotlight.PortfolioSpotlightAsyncResponse,
    response_model_exclude_none=True,
)
async def spotlight_portfolio_async(
    background_tasks: BackgroundTasks,
    response: Response,
    request: schemas_spotlight.PortfolioSpotlightRequest | None = Body(
        None,
        description="The portfolio spotlight request. Required when starting a task; omitted when polling.",
    ),
    task_id: str = Query("", description="Task ID returned by a previous call to this endpoint."),
) -> schemas_spotlight.PortfolioSpotlightAsyncResponse:
    """Start a portfolio-spotlight task or poll a previously started task."""

    normalized_task_id = task_id.strip()
    if normalized_task_id:
        task_entry = await router_async_task.load_task(normalized_task_id, _TASK_TYPE)
        task_state = task_entry.state
        task_info = async_task.AsyncTaskInfo(task_id=normalized_task_id, state=task_state)
        if task_state == async_task.TASK_STATE_RUNNING:
            response.status_code = status.HTTP_202_ACCEPTED
            return schemas_spotlight.PortfolioSpotlightAsyncResponse(
                status=status.HTTP_202_ACCEPTED,
                message="Task is running",
                extra=task_info,
            )
        if task_state == async_task.TASK_STATE_FAILED:
            failure_status = router_async_task.failure_status(task_entry)
            response.status_code = failure_status
            return schemas_spotlight.PortfolioSpotlightAsyncResponse(
                status=failure_status,
                message=task_entry.message or "Task failed",
                extra=task_info,
            )

        result = schemas_spotlight.PortfolioSpotlightResponse.model_validate(task_entry.result)
        return schemas_spotlight.PortfolioSpotlightAsyncResponse(
            status=result.status,
            message=result.message,
            data=result.data,
            extra=task_info,
        )

    if request is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Request body is required when starting a task",
        )

    new_task_id = await router_async_task.start_task(_TASK_TYPE)
    background_tasks.add_task(_run_task, new_task_id, request)
    response.status_code = status.HTTP_202_ACCEPTED
    return schemas_spotlight.PortfolioSpotlightAsyncResponse(
        status=status.HTTP_202_ACCEPTED,
        message="Task started",
        extra=async_task.AsyncTaskInfo(
            task_id=new_task_id,
            state=async_task.TASK_STATE_RUNNING,
        ),
    )
