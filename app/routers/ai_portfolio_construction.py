import logging

from fastapi import APIRouter, BackgroundTasks, Body, HTTPException, Query, Response, status

from ..schemas import ai_portfolio_construction as schemas_construction
from ..schemas import async_task
from ..schemas.base_req_resp import BaseResponse
from ..services import msai_build_portfolio as service_build_portfolio
from ..services import portfolio_verification
from . import async_task as router_async_task

router = APIRouter(prefix="/ai", tags=["ai"])

_TASK_TYPE = "build_portfolio"


async def _get_build_portfolio_result(
    req: schemas_construction.BuildPortfolioRequest,
) -> schemas_construction.BuildPortfolioResponse:
    try:
        result = await service_build_portfolio.ai_build_portfolio(
            portfolio=req.current_allocation,
            country=req.country,
            investor_theme=req.investor_theme,
        )
    except portfolio_verification.PortfolioInputError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except (
        portfolio_verification.PortfolioVerificationError,
        service_build_portfolio.PortfolioConstructionAIError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    return schemas_construction.BuildPortfolioResponse(status=200, message="ok", data=result)


@router.post(
    "/build_portfolio",
    response_model=schemas_construction.BuildPortfolioResponse,
    response_model_exclude_none=True,
    responses={
        422: {
            "model": BaseResponse,
            "description": "The request or verified seed holdings are invalid.",
        },
        502: {
            "model": BaseResponse,
            "description": "Market verification, AI execution, or structured output failed.",
        },
    },
)
async def build_portfolio(
    req: schemas_construction.BuildPortfolioRequest = Body(description="The build portfolio request."),
) -> schemas_construction.BuildPortfolioResponse:
    """Build one research-backed target portfolio and budget-aware action plan."""

    return await _get_build_portfolio_result(req)


async def _run_build_portfolio_task(
    task_id: str,
    req: schemas_construction.BuildPortfolioRequest,
) -> None:
    try:
        result = await _get_build_portfolio_result(req)
    except HTTPException as exc:
        await router_async_task.fail_task(
            task_id,
            _TASK_TYPE,
            status_code=exc.status_code,
            message=str(exc.detail),
        )
        return
    except Exception:
        logging.exception("Build portfolio task '%s' failed.", task_id)
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
    )


@router.post(
    "/build_portfolio_async",
    response_model=schemas_construction.BuildPortfolioAsyncResponse,
    response_model_exclude_none=True,
    responses={
        202: {
            "model": schemas_construction.BuildPortfolioAsyncResponse,
            "description": "The portfolio-construction task started or is still running.",
        },
        404: {"model": BaseResponse, "description": "The task was not found."},
        422: {
            "model": schemas_construction.BuildPortfolioAsyncResponse | BaseResponse,
            "description": "The start request or verified seed holdings are invalid.",
        },
        500: {
            "model": schemas_construction.BuildPortfolioAsyncResponse | BaseResponse,
            "description": "The background task failed unexpectedly.",
        },
        502: {
            "model": schemas_construction.BuildPortfolioAsyncResponse,
            "description": "Market verification, AI execution, or structured output failed.",
        },
    },
)
async def build_portfolio_async(
    background_tasks: BackgroundTasks,
    response: Response,
    req: schemas_construction.BuildPortfolioRequest | None = Body(
        None,
        description="The build portfolio request. Required when starting a task; not required when polling.",
    ),
    task_id: str = Query("", description="Task ID returned by a previous call to this endpoint."),
) -> schemas_construction.BuildPortfolioAsyncResponse:
    """Start a portfolio-construction task or poll a previously started task."""

    task_id = task_id.strip()
    if task_id:
        task_entry = await router_async_task.load_task(task_id, _TASK_TYPE)
        task_state = task_entry.state
        task_info = async_task.AsyncTaskInfo(task_id=task_id, state=task_state)
        if task_state == async_task.TASK_STATE_RUNNING:
            response.status_code = status.HTTP_202_ACCEPTED
            return schemas_construction.BuildPortfolioAsyncResponse(
                status=status.HTTP_202_ACCEPTED,
                message="Task is running",
                extra=task_info,
            )
        if task_state == async_task.TASK_STATE_FAILED:
            failure_status = router_async_task.failure_status(task_entry)
            response.status_code = failure_status
            return schemas_construction.BuildPortfolioAsyncResponse(
                status=failure_status,
                message=task_entry.message or "Task failed",
                extra=task_info,
            )

        result = schemas_construction.BuildPortfolioResponse.model_validate(task_entry.result)
        return schemas_construction.BuildPortfolioAsyncResponse(
            status=result.status,
            message=result.message,
            data=result.data,
            extra=task_info,
        )

    if req is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Request body is required when starting a task",
        )

    task_id = await router_async_task.start_task(_TASK_TYPE)
    background_tasks.add_task(_run_build_portfolio_task, task_id, req)
    response.status_code = status.HTTP_202_ACCEPTED
    return schemas_construction.BuildPortfolioAsyncResponse(
        status=status.HTTP_202_ACCEPTED,
        message="Task started",
        extra=async_task.AsyncTaskInfo(task_id=task_id, state=async_task.TASK_STATE_RUNNING),
    )
