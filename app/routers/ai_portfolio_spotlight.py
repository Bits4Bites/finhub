import logging

from fastapi import APIRouter, BackgroundTasks, Body, HTTPException, Query, Request, Response, status

from .. import config
from ..schemas import ai_portfolio_spotlight as schemas_spotlight
from ..schemas import async_task
from ..schemas.base_req_resp import BaseResponse
from ..services import msai_spotlight_portfolio as services_spotlight
from ..services import portfolio_verification
from . import async_task as router_async_task
from . import proxy_handler

router = APIRouter(prefix="/ai", tags=["ai"])

_TASK_TYPE = "spotlight_portfolio"
_ASYNC_RESPONSES = {
    202: {
        "model": schemas_spotlight.PortfolioSpotlightAsyncResponse,
        "description": "The portfolio-spotlight task started or is still running.",
    },
    404: {"model": BaseResponse, "description": "The task was not found."},
    422: router_async_task.validation_error_response(
        "The start request, verified portfolio input, or proxy forward-timeout header is invalid.",
        schemas_spotlight.PortfolioSpotlightAsyncResponse,
        BaseResponse,
    ),
    500: {
        "model": schemas_spotlight.PortfolioSpotlightAsyncResponse | BaseResponse,
        "description": "The background task or retained task state failed unexpectedly.",
    },
    502: {
        "model": schemas_spotlight.PortfolioSpotlightAsyncResponse | BaseResponse,
        "description": (
            "Market verification, AI execution, structured output, final validation, or proxy forwarding failed."
        ),
    },
}


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
    responses={
        422: router_async_task.validation_error_response(
            "The request, verified portfolio input, or proxy forward-timeout header is invalid.",
            BaseResponse,
        ),
        502: {
            "model": BaseResponse,
            "description": (
                "Market verification, AI execution, structured output, final validation, or proxy forwarding failed."
            ),
        },
    },
)
async def spotlight_portfolio(
    http_request: Request,
    request: schemas_spotlight.PortfolioSpotlightRequest = Body(description="The portfolio spotlight request."),
) -> schemas_spotlight.PortfolioSpotlightResponse | Response:
    """Return a concise, verified spotlight of portfolio risks and actions.

    Args:
        http_request: Incoming HTTP request used when an AI-task proxy node is
            configured.
        request: Validated country, investor theme, and one or more unique
            holdings, with at least one positive-share position.

    Returns:
        HTTP 200 with the verified portfolio snapshot, severity-ranked risks,
        recommended actions, rebalance flag, data gaps, warnings, and cited
        sources. Redirect proxy mode instead returns HTTP 307, while forward
        mode relays the upstream response and status.

    Raises:
        HTTPException: With HTTP 422 when portfolio input is rejected, or HTTP
            502 when market verification, provider execution, structured
            output, or provider-independent final result validation fails.

    Notes:
        Zero-share entries are excluded and every positive holding is verified
        against current market data before cached analysis can be reused.
        Duplicate normalized tickers and requests without a positive holding
        fail request validation with HTTP 422. Unexpected local failures return
        HTTP 500, authentication can return HTTP 401, and a configured proxy
        short-circuits local analysis after request validation.
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
    request: schemas_spotlight.PortfolioSpotlightRequest,
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
        logging.exception("Spotlight portfolio task '%s' failed.", task_id)
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
        status_code=result.status,
        message=result.message,
    )


async def _poll_task(
    task_id: str,
    response: Response,
) -> schemas_spotlight.PortfolioSpotlightAsyncResponse:
    task_entry = await router_async_task.task_store.load(task_id, _TASK_TYPE)
    task_state = task_entry.state
    task_info = async_task.AsyncTaskInfo(task_id=task_id, state=task_state)
    if task_state == async_task.TASK_STATE_RUNNING:
        response.status_code = status.HTTP_202_ACCEPTED
        return schemas_spotlight.PortfolioSpotlightAsyncResponse(
            status=status.HTTP_202_ACCEPTED,
            message="Task is running",
            extra=task_info,
        )
    if task_state == async_task.TASK_STATE_FAILED:
        failure_status = task_entry.failure_http_status
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


@router.post(
    "/start_spotlight_portfolio_async",
    response_model=schemas_spotlight.PortfolioSpotlightAsyncResponse,
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
async def start_spotlight_portfolio_async(
    background_tasks: BackgroundTasks,
    response: Response,
    http_request: Request,
    request: schemas_spotlight.PortfolioSpotlightRequest | None = Body(
        None,
        description="The portfolio spotlight request.",
    ),
) -> schemas_spotlight.PortfolioSpotlightAsyncResponse | Response:
    """Start or reuse an asynchronous portfolio-spotlight task.

    Args:
        background_tasks: FastAPI task collector that runs a newly accepted
            spotlight after the start response is prepared.
        response: Outgoing response whose HTTP status reflects the returned task
            state.
        http_request: Incoming HTTP request used when an AI-task proxy node is
            configured.
        request: Validated spotlight request. ``None`` represents an omitted or
            JSON-null body so the endpoint can preserve its HTTP 400 contract.

    Returns:
        HTTP 202 with a task ID for a new or already-running task. Repeating an
        equivalent request while its state is retained returns HTTP 200 with the
        completed spotlight or the stored HTTP 422, 502, or 500 failure.
        Redirect proxy mode returns HTTP 307; forward mode relays the upstream
        response and status.

    Raises:
        HTTPException: With HTTP 400 when the local request body is missing or
            null, HTTP 404 if a reused task expires before it can be read, or
            HTTP 500 for invalid retained task state.

    Notes:
        OpenAPI marks the body as required even though the nullable handler
        parameter distinguishes a missing body (HTTP 400) from an invalid body
        (HTTP 422). Equivalent validated requests are deduplicated across
        running, completed, and failed states. Each state expires one hour after
        its latest lifecycle update; after expiry the request can run again and
        polling returns HTTP 404. Portfolio input failures become HTTP 422,
        verification, provider, structured-output, and final-validation
        failures become HTTP 502, and unexpected failures become HTTP 500.
        Authentication can return HTTP 401 before invocation.
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
    return schemas_spotlight.PortfolioSpotlightAsyncResponse(
        status=status.HTTP_202_ACCEPTED,
        message="Task started",
        extra=async_task.AsyncTaskInfo(
            task_id=new_task_id,
            state=async_task.TASK_STATE_RUNNING,
        ),
    )


@router.post(
    "/poll_spotlight_portfolio_async",
    response_model=schemas_spotlight.PortfolioSpotlightAsyncResponse,
    response_model_exclude_none=True,
    responses=_ASYNC_RESPONSES,
)
async def poll_spotlight_portfolio_async(
    response: Response,
    http_request: Request,
    task_id: str = Query(description="Task ID returned by the corresponding start endpoint."),
) -> schemas_spotlight.PortfolioSpotlightAsyncResponse | Response:
    """Read the current public state of a portfolio-spotlight task.

    Args:
        response: Outgoing response whose HTTP status is updated to match the
            task state.
        http_request: Incoming HTTP request used when an AI-task proxy node is
            configured.
        task_id: Identifier returned by ``start_spotlight_portfolio_async``;
            surrounding whitespace is ignored.

    Returns:
        HTTP 202 with ``RUNNING``, HTTP 200 with the completed spotlight, or
        ``FAILED`` with the stored HTTP 422, 502, or 500 status. Redirect proxy
        mode returns HTTP 307; forward mode relays the upstream response and
        status.

    Raises:
        HTTPException: With HTTP 404 when the task is unknown, belongs to
            another task type, or has expired; or HTTP 500 when retained state
            is invalid. Omitting the required query parameter returns HTTP 422
            before this function is called.

    Notes:
        Task states expire one hour after their latest lifecycle update. Polling
        never restarts expired analysis. Authentication can return HTTP 401
        before invocation.
    """

    proxy_response = await proxy_handler.handle_if_proxy(
        config.settings_finhub_proxy.proxy_mode,
        config.settings_finhub_proxy.url_ai_task_node,
        http_request,
    )
    if proxy_response is not None:
        return proxy_response

    return await _poll_task(task_id.strip(), response)
