import logging

from fastapi import APIRouter, BackgroundTasks, Body, HTTPException, Query, Response, status

from ..schemas import ai_dividend as schemas_ai_dividend
from ..schemas import async_task
from ..services import msai_analyze_div_event as services_dividend
from . import async_task as router_async_task

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
        await router_async_task.fail_task(
            task_id,
            _TASK_TYPE,
            status_code=exc.status_code,
            message=str(exc.detail),
        )
        return
    except Exception:
        logging.exception("Analyze dividend event task '%s' failed.", task_id)
        await router_async_task.fail_task(
            task_id,
            _TASK_TYPE,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
        return

    if result.status == status.HTTP_200_OK:
        await router_async_task.complete_task(
            task_id,
            _TASK_TYPE,
            result,
            status_code=result.status,
            message=result.message,
        )
    else:
        await router_async_task.fail_task(
            task_id,
            _TASK_TYPE,
            status_code=result.status,
            message=result.message,
            result=result,
        )


@router.post(
    "/analyze_dividend_event_async",
    response_model=schemas_ai_dividend.AnalyzeDividendEventAsyncResponse,
    response_model_exclude_none=True,
)
async def analyze_dividend_event_async(
    background_tasks: BackgroundTasks,
    response: Response,
    request: schemas_ai_dividend.AnalyzeDividendEventRequest | None = Body(
        None,
        description="The dividend-event analysis request. Required when starting a task; omitted when polling.",
    ),
    task_id: str = Query("", description="Task ID returned by a previous call to this endpoint."),
) -> schemas_ai_dividend.AnalyzeDividendEventAsyncResponse:
    normalized_task_id = task_id.strip()
    if normalized_task_id:
        task_entry = await router_async_task.load_task(normalized_task_id, _TASK_TYPE)
        task_state = task_entry.state
        task_info = async_task.AsyncTaskInfo(task_id=normalized_task_id, state=task_state)
        if task_state == async_task.TASK_STATE_RUNNING:
            response.status_code = status.HTTP_202_ACCEPTED
            return schemas_ai_dividend.AnalyzeDividendEventAsyncResponse(
                status=status.HTTP_202_ACCEPTED,
                message="Task is running",
                extra=task_info,
            )
        if task_state == async_task.TASK_STATE_FAILED:
            failure_status = router_async_task.failure_status(task_entry)
            response.status_code = failure_status
            if task_entry.result is not None:
                result = schemas_ai_dividend.AnalyzeDividendEventResponse.model_validate(task_entry.result)
                return schemas_ai_dividend.AnalyzeDividendEventAsyncResponse(
                    status=failure_status,
                    message=result.message,
                    data=result.data,
                    extra=task_info,
                )
            return schemas_ai_dividend.AnalyzeDividendEventAsyncResponse(
                status=failure_status,
                message=task_entry.message or "Task failed",
                extra=task_info,
            )

        result = schemas_ai_dividend.AnalyzeDividendEventResponse.model_validate(task_entry.result)
        return schemas_ai_dividend.AnalyzeDividendEventAsyncResponse(
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

    new_task_id, is_new = await router_async_task.start_task(_TASK_TYPE, request)
    if not is_new:
        return await analyze_dividend_event_async(
            background_tasks=background_tasks,
            response=response,
            request=request,
            task_id=new_task_id,
        )

    background_tasks.add_task(_run_task, new_task_id, request)
    response.status_code = status.HTTP_202_ACCEPTED
    return schemas_ai_dividend.AnalyzeDividendEventAsyncResponse(
        status=status.HTTP_202_ACCEPTED,
        message="Task started",
        extra=async_task.AsyncTaskInfo(
            task_id=new_task_id,
            state=async_task.TASK_STATE_RUNNING,
        ),
    )
