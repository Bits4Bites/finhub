import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, HTTPException, Response, status

from ..schemas import ai_dividend as schemas_ai_dividend
from ..schemas import async_task
from ..schemas import events as schemas_events
from ..services import msai_analyze_div_event as services_dividend
from ..utils import cache

router = APIRouter(prefix="/ai", tags=["ai"])

_TASK_TYPE = "analyze_dividend_event"


async def _analyze(
    request: schemas_ai_dividend.AnalyzeDividendEventRequest,
) -> schemas_ai_dividend.AnalyzeDividendEventResponse:
    try:
        result = await services_dividend.ai_analyze_div_event(
            symbol=request.symbol.upper(),
            ex_date=request.ex_date,
            dividend_amount=request.dividend_amount,
            transaction_costs=request.transaction_costs,
            holding_period_days=request.holding_period_days,
        )
    except services_dividend.DividendEventInputError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except services_dividend.DividendEventInsufficientDataError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except services_dividend.DividendEventAIError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    if result.analysis_status == "Failed":
        return schemas_ai_dividend.AnalyzeDividendEventResponse(
            status=status.HTTP_502_BAD_GATEWAY,
            message=result.failure_reason or "Dividend analysis failed",
            data=result,
        )
    return schemas_ai_dividend.AnalyzeDividendEventResponse(
        status=status.HTTP_200_OK,
        message="ok",
        data=result,
    )


@router.post(
    "/analyze_dividend_event",
    response_model=schemas_ai_dividend.AnalyzeDividendEventResponse,
    response_model_exclude_none=True,
)
async def analyze_dividend_event(
    request: schemas_ai_dividend.AnalyzeDividendEventRequest,
    response: Response,
) -> schemas_ai_dividend.AnalyzeDividendEventResponse:
    result = await _analyze(request)
    response.status_code = result.status
    return result


async def _run_task(
    task_id: str,
    request: schemas_ai_dividend.AnalyzeDividendEventRequest,
) -> None:
    try:
        result = await _analyze(request)
    except HTTPException as exc:
        await cache.set(
            task_id,
            {
                "task_type": _TASK_TYPE,
                "state": async_task.TASK_STATE_FAILED,
                "status": exc.status_code,
                "message": str(exc.detail),
            },
            ttl=async_task.ASYNC_TASK_TTL,
        )
        return
    except Exception:
        logging.exception("Analyze dividend event task '%s' failed.", task_id)
        await cache.set(
            task_id,
            {
                "task_type": _TASK_TYPE,
                "state": async_task.TASK_STATE_FAILED,
                "status": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "message": "Task failed",
            },
            ttl=async_task.ASYNC_TASK_TTL,
        )
        return

    task_state = (
        async_task.TASK_STATE_COMPLETED if result.status == status.HTTP_200_OK else async_task.TASK_STATE_FAILED
    )
    await cache.set(
        task_id,
        {
            "task_type": _TASK_TYPE,
            "state": task_state,
            "status": result.status,
            "message": result.message,
            "result": result.model_dump(mode="json"),
        },
        ttl=async_task.ASYNC_TASK_TTL,
    )


@router.post(
    "/analyze_dividend_event_async",
    response_model=schemas_ai_dividend.AnalyzeDividendEventAsyncResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_analyze_dividend_event_task(
    request: schemas_ai_dividend.AnalyzeDividendEventRequest,
    background_tasks: BackgroundTasks,
) -> schemas_ai_dividend.AnalyzeDividendEventAsyncResponse:
    task_id = str(uuid.uuid4())
    await cache.set(
        task_id,
        {
            "task_type": _TASK_TYPE,
            "state": async_task.TASK_STATE_RUNNING,
        },
        ttl=async_task.ASYNC_TASK_TTL,
    )
    background_tasks.add_task(_run_task, task_id, request)
    return schemas_ai_dividend.AnalyzeDividendEventAsyncResponse(
        status=status.HTTP_202_ACCEPTED,
        message="Task started",
        extra=schemas_events.AsyncTaskInfo(
            task_id=task_id,
            state=async_task.TASK_STATE_RUNNING,
        ),
    )


@router.get(
    "/analyze_dividend_event_async/{task_id}",
    response_model=schemas_ai_dividend.AnalyzeDividendEventAsyncResponse,
    response_model_exclude_none=True,
)
async def get_analyze_dividend_event_task(
    task_id: str,
    response: Response,
) -> schemas_ai_dividend.AnalyzeDividendEventAsyncResponse:
    normalized_task_id = task_id.strip()
    task_entry = await cache.get(normalized_task_id)
    if not isinstance(task_entry, dict) or task_entry.get("task_type") != _TASK_TYPE:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    task_state = task_entry.get("state")
    if task_state not in {
        async_task.TASK_STATE_RUNNING,
        async_task.TASK_STATE_COMPLETED,
        async_task.TASK_STATE_FAILED,
    }:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Invalid task state")

    task_info = schemas_events.AsyncTaskInfo(task_id=normalized_task_id, state=task_state)
    if task_state == async_task.TASK_STATE_RUNNING:
        response.status_code = status.HTTP_202_ACCEPTED
        return schemas_ai_dividend.AnalyzeDividendEventAsyncResponse(
            status=status.HTTP_202_ACCEPTED,
            message="Task is running",
            extra=task_info,
        )
    if task_state == async_task.TASK_STATE_FAILED:
        raw_failure_status = task_entry.get("status")
        failure_status = (
            raw_failure_status
            if isinstance(raw_failure_status, int) and 400 <= raw_failure_status <= 599
            else status.HTTP_500_INTERNAL_SERVER_ERROR
        )
        response.status_code = failure_status
        failed_result = task_entry.get("result")
        if isinstance(failed_result, dict):
            result = schemas_ai_dividend.AnalyzeDividendEventResponse.model_validate(failed_result)
            return schemas_ai_dividend.AnalyzeDividendEventAsyncResponse(
                status=failure_status,
                message=result.message,
                data=result.data,
                extra=task_info,
            )
        return schemas_ai_dividend.AnalyzeDividendEventAsyncResponse(
            status=failure_status,
            message=str(task_entry.get("message", "Task failed")),
            extra=task_info,
        )
    if not isinstance(task_entry.get("result"), dict):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Invalid task state")

    result = schemas_ai_dividend.AnalyzeDividendEventResponse.model_validate(task_entry["result"])
    return schemas_ai_dividend.AnalyzeDividendEventAsyncResponse(
        status=result.status,
        message=result.message,
        data=result.data,
        extra=task_info,
    )
