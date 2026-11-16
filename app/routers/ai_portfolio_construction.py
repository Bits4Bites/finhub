import logging

from fastapi import APIRouter, BackgroundTasks, Body, HTTPException, Query, Request, Response, status

from .. import config
from ..schemas import ai_portfolio_construction as schemas_construction
from ..schemas import async_task
from ..schemas.base_req_resp import BaseResponse
from ..services import msai_build_portfolio as service_build_portfolio
from ..services import portfolio_verification
from . import async_task as router_async_task
from . import proxy_handler

router = APIRouter(prefix="/ai", tags=["ai"])

_TASK_TYPE = "build_portfolio"
_ASYNC_RESPONSES = {
    202: {
        "model": schemas_construction.BuildPortfolioAsyncResponse,
        "description": "The portfolio-construction task started or is still running.",
    },
    404: {"model": BaseResponse, "description": "The task was not found."},
    422: router_async_task.validation_error_response(
        "The start request, verified seed holdings, or proxy forward-timeout header is invalid.",
        schemas_construction.BuildPortfolioAsyncResponse,
        BaseResponse,
    ),
    500: {
        "model": schemas_construction.BuildPortfolioAsyncResponse | BaseResponse,
        "description": "The background task failed unexpectedly.",
    },
    502: {
        "model": schemas_construction.BuildPortfolioAsyncResponse | BaseResponse,
        "description": "Market verification, AI execution, structured output, or proxy forwarding failed.",
    },
}


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
        422: router_async_task.validation_error_response(
            "The request, verified seed holdings, or proxy forward-timeout header is invalid.",
            BaseResponse,
        ),
        502: {
            "model": BaseResponse,
            "description": "Market verification, AI execution, structured output, or proxy forwarding failed.",
        },
    },
)
async def build_portfolio(
    http_request: Request,
    req: schemas_construction.BuildPortfolioRequest = Body(description="The build portfolio request."),
) -> schemas_construction.BuildPortfolioResponse | Response:
    """Construct a research-backed target portfolio for the caller.

    Args:
        http_request: Incoming HTTP request used when an AI-task proxy node is
            configured.
        req: Validated country, investor theme, and optional starting
            allocation. Zero-share positions are ignored; a request with no
            positive-share positions is constructed from scratch.

    Returns:
        HTTP 200 with a ``Scratch`` or ``Seeded`` portfolio construction. The
        action plan can be null when no usable funding is available. Redirect
        proxy mode instead returns HTTP 307, while forward mode relays the
        upstream response and status.

    Raises:
        HTTPException: With HTTP 422 when portfolio or budget input is rejected,
            or HTTP 502 when market verification, AI processing, structured
            output, target-price verification, or final result validation
            fails.

    Notes:
        Positive seed holdings are verified against market data before they are
        used. Scratch construction does not verify zero-share seed entries;
        funded action plans verify target prices. Request-schema errors return
        HTTP 422 before local construction, unexpected local errors return HTTP
        500, and application authentication can return HTTP 401. A configured
        proxy short-circuits local construction after request validation.
    """

    proxy_response = await proxy_handler.handle_if_proxy(
        config.settings_finhub_proxy.proxy_mode,
        config.settings_finhub_proxy.url_ai_task_node,
        http_request,
    )
    if proxy_response is not None:
        return proxy_response

    return await _get_build_portfolio_result(req)


async def _run_build_portfolio_task(
    task_id: str,
    req: schemas_construction.BuildPortfolioRequest,
) -> None:
    try:
        result = await _get_build_portfolio_result(req)
    except HTTPException as exc:
        await router_async_task.task_store.fail(
            task_id,
            _TASK_TYPE,
            status_code=exc.status_code,
            message=str(exc.detail),
        )
        return
    except Exception:
        logging.exception("Build portfolio task '%s' failed.", task_id)
        await router_async_task.task_store.fail(
            task_id,
            _TASK_TYPE,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
        return

    await router_async_task.task_store.complete(
        task_id,
        _TASK_TYPE,
        result,
    )


async def _poll_task(
    task_id: str,
    response: Response,
) -> schemas_construction.BuildPortfolioAsyncResponse:
    task_entry = await router_async_task.task_store.load(task_id, _TASK_TYPE)
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
        failure_status = task_entry.failure_http_status
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


@router.post(
    "/start_build_portfolio_async",
    response_model=schemas_construction.BuildPortfolioAsyncResponse,
    response_model_exclude_none=True,
    responses={
        400: {
            "model": BaseResponse,
            "description": "A request body is required to start a task.",
        },
        **_ASYNC_RESPONSES,
    },
    openapi_extra={"requestBody": {"required": True}},
)
async def start_build_portfolio_async(
    background_tasks: BackgroundTasks,
    response: Response,
    http_request: Request,
    req: schemas_construction.BuildPortfolioRequest | None = Body(
        None,
        description="The build portfolio request.",
    ),
) -> schemas_construction.BuildPortfolioAsyncResponse | Response:
    """Start or reuse an asynchronous portfolio-construction task.

    Args:
        background_tasks: FastAPI task collector that runs a newly accepted
            construction after the start response is prepared.
        response: Outgoing response whose HTTP status reflects the returned task
            state.
        http_request: Incoming HTTP request used when an AI-task proxy node is
            configured.
        req: Validated construction request. ``None`` represents an omitted or
            JSON-null body so the endpoint can preserve its HTTP 400 contract.

    Returns:
        HTTP 202 with a task ID for a new or already-running task. Repeating an
        equivalent request while its state is retained returns that task's
        current outcome: HTTP 200 with completed construction data, or the
        stored HTTP 422, 502, or 500 failure. Redirect proxy mode returns HTTP
        307; forward mode relays the upstream response and status.

    Raises:
        HTTPException: With HTTP 400 when the local request body is missing or
            null, HTTP 404 if a reused task expires before it can be read, or
            HTTP 500 for invalid retained task state.

    Notes:
        OpenAPI marks the body as required even though the nullable handler
        parameter is necessary to distinguish a missing body (HTTP 400) from an
        invalid body (HTTP 422). Equivalent validated requests are deduplicated
        while their task state exists. Running, completed, and failed states
        expire one hour after their latest lifecycle update; after expiry the
        request can be scheduled again and polling returns HTTP 404. Background
        portfolio input failures become HTTP 422, verification or AI/final
        validation failures become HTTP 502, and unexpected failures become
        HTTP 500. Authentication can return HTTP 401 before invocation.
    """

    proxy_response = await proxy_handler.handle_if_proxy(
        config.settings_finhub_proxy.proxy_mode,
        config.settings_finhub_proxy.url_ai_task_node,
        http_request,
    )
    if proxy_response is not None:
        return proxy_response

    if req is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Request body is required when starting a task",
        )

    task_id, is_new = await router_async_task.task_store.start(_TASK_TYPE, req)
    if not is_new:
        return await _poll_task(task_id, response)

    background_tasks.add_task(_run_build_portfolio_task, task_id, req)
    response.status_code = status.HTTP_202_ACCEPTED
    return schemas_construction.BuildPortfolioAsyncResponse(
        status=status.HTTP_202_ACCEPTED,
        message="Task started",
        extra=async_task.AsyncTaskInfo(task_id=task_id, state=async_task.TASK_STATE_RUNNING),
    )


@router.post(
    "/poll_build_portfolio_async",
    response_model=schemas_construction.BuildPortfolioAsyncResponse,
    response_model_exclude_none=True,
    responses=_ASYNC_RESPONSES,
)
async def poll_build_portfolio_async(
    response: Response,
    http_request: Request,
    task_id: str = Query(description="Task ID returned by the corresponding start endpoint."),
) -> schemas_construction.BuildPortfolioAsyncResponse | Response:
    """Read the current public state of a portfolio-construction task.

    Args:
        response: Outgoing response whose HTTP status is updated to match the
            task state.
        http_request: Incoming HTTP request used when an AI-task proxy node is
            configured.
        task_id: Identifier returned by ``start_build_portfolio_async``;
            surrounding whitespace is ignored.

    Returns:
        HTTP 202 with ``RUNNING``, HTTP 200 with completed construction data, or
        ``FAILED`` with the stored HTTP 422, 502, or 500 status. Redirect proxy
        mode returns HTTP 307; forward mode relays the upstream response and
        status.

    Raises:
        HTTPException: With HTTP 404 when the task is unknown, belongs to
            another task type, or has expired; or HTTP 500 when retained state
            is invalid. Omitting the required query parameter returns HTTP 422
            before this function is called.

    Notes:
        Task states expire one hour after their latest lifecycle update. The
        endpoint does not restart expired work; callers must submit the start
        request again. Authentication can return HTTP 401 before invocation.
    """

    proxy_response = await proxy_handler.handle_if_proxy(
        config.settings_finhub_proxy.proxy_mode,
        config.settings_finhub_proxy.url_ai_task_node,
        http_request,
    )
    if proxy_response is not None:
        return proxy_response

    return await _poll_task(task_id.strip(), response)
