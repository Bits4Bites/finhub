import logging

from fastapi import APIRouter, BackgroundTasks, Body, HTTPException, Query, Request, Response, status

from .. import config
from ..schemas import ai_dividend as schemas_ai_dividend
from ..schemas import async_task
from ..schemas.base_req_resp import BaseResponse
from ..services import ai_helper
from ..services import msai_analyze_div_event as services_dividend
from . import async_task as router_async_task
from . import proxy_handler

router = APIRouter(prefix="/ai", tags=["ai"])

_TASK_TYPE = "analyze_dividend_event"
_SYNC_RESPONSES = {
    400: {"model": BaseResponse, "description": "The dividend request or resolved security is invalid."},
    422: router_async_task.validation_error_response(
        "The request body or proxy forward-timeout header is invalid, or market history is insufficient.",
        BaseResponse,
    ),
    500: {"model": BaseResponse, "description": "An unexpected dependency or server failure occurred."},
    502: {
        "model": schemas_ai_dividend.AnalyzeDividendEventResponse | BaseResponse,
        "description": "The AI provider, rate-limit budget, structured analysis, or proxy forwarding failed.",
    },
}
_ASYNC_STATE_RESPONSES = {
    202: {
        "model": schemas_ai_dividend.AnalyzeDividendEventAsyncResponse,
        "description": "The dividend-analysis task started or is still running.",
    },
    400: {
        "model": schemas_ai_dividend.AnalyzeDividendEventAsyncResponse | BaseResponse,
        "description": "The task request or resolved security is invalid.",
    },
    404: {"model": BaseResponse, "description": "The task was not found."},
    422: router_async_task.validation_error_response(
        "The request or proxy forward-timeout header is invalid, or market history is insufficient.",
        schemas_ai_dividend.AnalyzeDividendEventAsyncResponse,
        BaseResponse,
    ),
    500: {
        "model": schemas_ai_dividend.AnalyzeDividendEventAsyncResponse | BaseResponse,
        "description": "The task state is invalid or the background task failed unexpectedly.",
    },
    502: {
        "model": schemas_ai_dividend.AnalyzeDividendEventAsyncResponse | BaseResponse,
        "description": "The AI provider, rate-limit budget, structured analysis, or proxy forwarding failed.",
    },
}
_ASYNC_START_RESPONSES = {
    **_ASYNC_STATE_RESPONSES,
}


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
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    except (services_dividend.DividendEventAIError, ai_helper.LLMRateLimitError) as exc:
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
    responses=_SYNC_RESPONSES,
)
async def analyze_dividend_event(
    http_request: Request,
    request: schemas_ai_dividend.AnalyzeDividendEventRequest,
    response: Response,
) -> schemas_ai_dividend.AnalyzeDividendEventResponse | Response:
    """Analyze one dividend event and return the assessment immediately.

    Args:
        http_request: Incoming HTTP request, forwarded when AI proxy mode is enabled.
        request: Validated symbol, ex-date, dividend amount, costs, and holding window.
        response: HTTP response whose status is aligned with the analysis outcome.

    Returns:
        A proxy response when configured; otherwise a dividend-analysis envelope.
        Complete analyses use status 200, while a validated failed analysis preserves
        its baseline data and uses status 502.

    Raises:
        HTTPException: With status 400 for invalid or unsupported input, 422 when
            market data cannot support a baseline, or 502 for AI-provider,
            rate-limit, or structured-analysis failures.

    Notes:
        Request-schema violations are reported as HTTP 422 before the handler runs.
        The symbol is uppercased before analysis.
    """
    proxy_response = await proxy_handler.handle_if_proxy(
        config.settings_finhub_proxy.proxy_mode,
        config.settings_finhub_proxy.url_ai_task_node,
        http_request,
    )
    if proxy_response is not None:
        return proxy_response

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
        await router_async_task.task_store.fail(
            task_id,
            _TASK_TYPE,
            status_code=exc.status_code,
            message=str(exc.detail),
        )
        return
    except Exception:
        logging.exception("Analyze dividend event task '%s' failed.", task_id)
        await router_async_task.task_store.fail(
            task_id,
            _TASK_TYPE,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
        return

    if result.status == status.HTTP_200_OK:
        await router_async_task.task_store.complete(
            task_id,
            _TASK_TYPE,
            result,
            status_code=result.status,
            message=result.message,
        )
    else:
        await router_async_task.task_store.fail(
            task_id,
            _TASK_TYPE,
            status_code=result.status,
            message=result.message,
            result=result,
        )


async def _poll_task(
    task_id: str,
    response: Response,
) -> schemas_ai_dividend.AnalyzeDividendEventAsyncResponse:
    task_entry = await router_async_task.task_store.load(task_id, _TASK_TYPE)
    task_state = task_entry.state
    task_info = async_task.AsyncTaskInfo(task_id=task_id, state=task_state)
    if task_state == async_task.TASK_STATE_RUNNING:
        response.status_code = status.HTTP_202_ACCEPTED
        return schemas_ai_dividend.AnalyzeDividendEventAsyncResponse(
            status=status.HTTP_202_ACCEPTED,
            message="Task is running",
            extra=task_info,
        )
    if task_state == async_task.TASK_STATE_FAILED:
        failure_status = task_entry.failure_http_status
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


@router.post(
    "/start_analyze_dividend_event_async",
    response_model=schemas_ai_dividend.AnalyzeDividendEventAsyncResponse,
    response_model_exclude_none=True,
    responses=_ASYNC_START_RESPONSES,
    openapi_extra={"requestBody": {"required": True}},
)
async def start_analyze_dividend_event_async(
    background_tasks: BackgroundTasks,
    response: Response,
    http_request: Request,
    request: schemas_ai_dividend.AnalyzeDividendEventRequest | None = Body(
        None,
        description="The dividend-event analysis request.",
    ),
) -> schemas_ai_dividend.AnalyzeDividendEventAsyncResponse | Response:
    """Start or reuse a background dividend-event analysis.

    Args:
        background_tasks: FastAPI scheduler used to run a newly created analysis.
        response: HTTP response updated to the task's current public status.
        http_request: Incoming HTTP request, forwarded when AI proxy mode is enabled.
        request: Required dividend-event request body.

    Returns:
        A proxy response when configured. A new or running task returns HTTP 202;
        an identical completed or failed task returns its persisted result and status.

    Raises:
        HTTPException: With status 400 and the established missing-body response
            when no JSON body is supplied, 404 if a reused task disappears, or 500
            when persisted task state is malformed.

    Notes:
        The OpenAPI contract marks the body as required while the optional Python
        annotation preserves the caller-visible HTTP 400 response for an omitted
        body. Identical running, completed, and failed requests are deduplicated.
        Invalid bodies are reported as HTTP 422.
    """
    proxy_response = await proxy_handler.handle_if_proxy(
        config.settings_finhub_proxy.proxy_mode,
        config.settings_finhub_proxy.url_ai_task_node,
        http_request,
    )
    if proxy_response is not None:
        return proxy_response

    if request is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Request body is required when starting a task",
        )

    new_task_id, is_new = await router_async_task.task_store.start(_TASK_TYPE, request)
    if not is_new:
        return await _poll_task(new_task_id, response)

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


@router.post(
    "/poll_analyze_dividend_event_async",
    response_model=schemas_ai_dividend.AnalyzeDividendEventAsyncResponse,
    response_model_exclude_none=True,
    responses=_ASYNC_STATE_RESPONSES,
)
async def poll_analyze_dividend_event_async(
    response: Response,
    http_request: Request,
    task_id: str = Query(description="Task ID returned by the corresponding start endpoint."),
) -> schemas_ai_dividend.AnalyzeDividendEventAsyncResponse | Response:
    """Return the current public state of a dividend-analysis task.

    Args:
        response: HTTP response updated to the running or failed task status.
        http_request: Incoming HTTP request, forwarded when AI proxy mode is enabled.
        task_id: Identifier returned by ``start_analyze_dividend_event_async``;
            surrounding whitespace is ignored.

    Returns:
        A proxy response when configured. Running tasks return HTTP 202, completed
        tasks return their analysis, and failed tasks return their stored 4xx/5xx
        status with any preserved baseline data.

    Raises:
        HTTPException: With status 404 when the task is missing or belongs to
            another workflow, or 500 when its persisted state is malformed.
    """
    proxy_response = await proxy_handler.handle_if_proxy(
        config.settings_finhub_proxy.proxy_mode,
        config.settings_finhub_proxy.url_ai_task_node,
        http_request,
    )
    if proxy_response is not None:
        return proxy_response

    return await _poll_task(task_id.strip(), response)
