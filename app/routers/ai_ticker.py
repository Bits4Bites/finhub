import logging

from fastapi import APIRouter, BackgroundTasks, Body, HTTPException, Query, Request, Response, status

from .. import config
from ..schemas import ai_ticker as schemas_ticker
from ..schemas import async_task
from ..schemas.base_req_resp import BaseResponse
from ..services import ai_helper
from ..services import msai_analyze_ticker as services_ticker
from . import async_task as router_async_task
from . import proxy_handler

router = APIRouter(prefix="/ai", tags=["ai"])

_TASK_TYPE = "analyze_ticker"
_SYNC_RESPONSES = {
    422: {
        "model": BaseResponse,
        "description": "The ticker symbol or optional holding is invalid.",
    },
    500: {"model": BaseResponse, "description": "An unexpected dependency or server failure occurred."},
    502: {
        "model": BaseResponse,
        "description": "Market verification, AI execution, rate-limit budget, or structured output failed.",
    },
}
_ASYNC_STATE_RESPONSES = {
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
        "description": "Market verification, AI execution, rate-limit budget, or structured output failed.",
    },
}
_ASYNC_START_RESPONSES = {
    400: {"model": BaseResponse, "description": "The required request body was omitted."},
    **_ASYNC_STATE_RESPONSES,
}


async def _analyze(
    request: schemas_ticker.AnalyzeTickerRequest,
) -> schemas_ticker.AnalyzeTickerResponse:
    try:
        result = await services_ticker.ai_analyze_ticker(
            symbol=request.symbol,
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
        ai_helper.LLMRateLimitError,
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
    responses=_SYNC_RESPONSES,
)
async def analyze_ticker(
    http_request: Request,
    request: schemas_ticker.AnalyzeTickerRequest = Body(description="The ticker analysis request."),
) -> schemas_ticker.AnalyzeTickerResponse | Response:
    """Return structured ticker research, four forecasts, and a recommendation.

    Args:
        http_request: Incoming HTTP request, forwarded when AI proxy mode is enabled.
        request: Validated ticker symbol and optional current-holding context.

    Returns:
        A proxy response when configured; otherwise a successful ticker-analysis
        envelope containing market data, research, forecasts, and a recommendation.

    Raises:
        HTTPException: With status 422 for invalid or unsupported ticker input, or
            502 when market verification, AI execution, the provider rate-limit
            budget, or structured output fails.

    Notes:
        Request-schema violations are reported as HTTP 422 before the handler runs.
        The request schema trims and uppercases the ticker symbol.
    """

    proxy_response = await proxy_handler.handle_if_proxy(
        config.settings_finhub_proxy.proxy_mode,
        config.settings_finhub_proxy.url_ai_task_node,
        http_request,
    )
    if proxy_response is not None:
        return proxy_response

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


async def _poll_task(
    task_id: str,
    response: Response,
) -> schemas_ticker.AnalyzeTickerAsyncResponse:
    task_entry = await router_async_task.load_task(task_id, _TASK_TYPE)
    task_state = task_entry.state
    task_info = async_task.AsyncTaskInfo(task_id=task_id, state=task_state)
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


@router.post(
    "/start_analyze_ticker_async",
    response_model=schemas_ticker.AnalyzeTickerAsyncResponse,
    response_model_exclude_none=True,
    responses=_ASYNC_START_RESPONSES,
    openapi_extra={"requestBody": {"required": True}},
)
async def start_analyze_ticker_async(
    background_tasks: BackgroundTasks,
    response: Response,
    http_request: Request,
    request: schemas_ticker.AnalyzeTickerRequest | None = Body(
        None,
        description="The ticker analysis request.",
    ),
) -> schemas_ticker.AnalyzeTickerAsyncResponse | Response:
    """Start or reuse a background ticker analysis.

    Args:
        background_tasks: FastAPI scheduler used to run a newly created analysis.
        response: HTTP response updated to the task's current public status.
        http_request: Incoming HTTP request, forwarded when AI proxy mode is enabled.
        request: Required ticker-analysis request body with optional holding context.

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

    new_task_id, is_new = await router_async_task.start_task(_TASK_TYPE, request)
    if not is_new:
        return await _poll_task(new_task_id, response)

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


@router.post(
    "/poll_analyze_ticker_async",
    response_model=schemas_ticker.AnalyzeTickerAsyncResponse,
    response_model_exclude_none=True,
    responses=_ASYNC_STATE_RESPONSES,
)
async def poll_analyze_ticker_async(
    response: Response,
    http_request: Request,
    task_id: str = Query(description="Task ID returned by the corresponding start endpoint."),
) -> schemas_ticker.AnalyzeTickerAsyncResponse | Response:
    """Return the current public state of a ticker-analysis task.

    Args:
        response: HTTP response updated to the running or failed task status.
        http_request: Incoming HTTP request, forwarded when AI proxy mode is enabled.
        task_id: Identifier returned by ``start_analyze_ticker_async``; surrounding
            whitespace is ignored.

    Returns:
        A proxy response when configured. Running tasks return HTTP 202, completed
        tasks return their analysis, and failed tasks return their stored 4xx/5xx
        status and caller-facing message.

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
