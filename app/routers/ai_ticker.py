import logging

from fastapi import APIRouter, BackgroundTasks, Body, HTTPException, Query, Response, status

from ..schemas import ai_ticker as schemas_ticker
from ..schemas import async_task
from ..schemas.base_req_resp import BaseResponse
from ..services import msai_analyze_ticker as services_ticker
from . import async_task as router_async_task

router = APIRouter(prefix="/ai", tags=["ai"])

_TASK_TYPE = "analyze_ticker"


async def _analyze(
    request: schemas_ticker.AnalyzeTickerRequest,
) -> schemas_ticker.AnalyzeTickerResponse:
    try:
        result = await services_ticker.ai_analyze_ticker(
            symbol=request.symbol,
            intent=request.intent,
            current_holding=request.current_holding,
        )
    except services_ticker.TickerInputError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except (
        services_ticker.TickerVerificationError,
        services_ticker.TickerAnalysisAIError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    return schemas_ticker.AnalyzeTickerResponse(
        status=status.HTTP_200_OK,
        message="ok",
        data=result,
    )


@router.post(
    "/analyze_ticker",
    response_model=schemas_ticker.AnalyzeTickerResponse,
    response_model_exclude_none=True,
    responses={
        422: {
            "model": BaseResponse,
            "description": "The ticker symbol or optional holding is invalid.",
        },
        502: {
            "model": BaseResponse,
            "description": "Market verification, AI execution, or structured output failed.",
        },
    },
)
async def analyze_ticker(
    request: schemas_ticker.AnalyzeTickerRequest = Body(description="The ticker analysis request."),
) -> schemas_ticker.AnalyzeTickerResponse:
    """Return structured ticker research, four forecasts, and a recommendation."""

    return await _analyze(request)


async def _run_task(
    task_id: str,
    request: schemas_ticker.AnalyzeTickerRequest,
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
        logging.exception("Analyze ticker task '%s' failed.", task_id)
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
    "/analyze_ticker_async",
    response_model=schemas_ticker.AnalyzeTickerAsyncResponse,
    response_model_exclude_none=True,
    responses={
        202: {
            "model": schemas_ticker.AnalyzeTickerAsyncResponse,
            "description": "The ticker-analysis task started or is still running.",
        },
        404: {"model": BaseResponse, "description": "The task was not found."},
        422: {
            "model": schemas_ticker.AnalyzeTickerAsyncResponse | BaseResponse,
            "description": "The ticker symbol or optional holding is invalid.",
        },
        500: {
            "model": schemas_ticker.AnalyzeTickerAsyncResponse | BaseResponse,
            "description": "The background task failed unexpectedly.",
        },
        502: {
            "model": schemas_ticker.AnalyzeTickerAsyncResponse,
            "description": "Market verification, AI execution, or structured output failed.",
        },
    },
)
async def analyze_ticker_async(
    background_tasks: BackgroundTasks,
    response: Response,
    request: schemas_ticker.AnalyzeTickerRequest | None = Body(
        None,
        description="The ticker analysis request. Required when starting a task; omitted when polling.",
    ),
    task_id: str = Query("", description="Task ID returned by a previous call to this endpoint."),
) -> schemas_ticker.AnalyzeTickerAsyncResponse:
    """Start a ticker-analysis task or poll a previously started task."""

    normalized_task_id = task_id.strip()
    if normalized_task_id:
        task_entry = await router_async_task.load_task(normalized_task_id, _TASK_TYPE)
        task_state = task_entry.state
        task_info = async_task.AsyncTaskInfo(task_id=normalized_task_id, state=task_state)
        if task_state == async_task.TASK_STATE_RUNNING:
            response.status_code = status.HTTP_202_ACCEPTED
            return schemas_ticker.AnalyzeTickerAsyncResponse(
                status=status.HTTP_202_ACCEPTED,
                message="Task is running",
                extra=task_info,
            )
        if task_state == async_task.TASK_STATE_FAILED:
            failure_status = router_async_task.failure_status(task_entry)
            response.status_code = failure_status
            return schemas_ticker.AnalyzeTickerAsyncResponse(
                status=failure_status,
                message=task_entry.message or "Task failed",
                extra=task_info,
            )

        result = schemas_ticker.AnalyzeTickerResponse.model_validate(task_entry.result)
        return schemas_ticker.AnalyzeTickerAsyncResponse(
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
    return schemas_ticker.AnalyzeTickerAsyncResponse(
        status=status.HTTP_202_ACCEPTED,
        message="Task started",
        extra=async_task.AsyncTaskInfo(
            task_id=new_task_id,
            state=async_task.TASK_STATE_RUNNING,
        ),
    )
