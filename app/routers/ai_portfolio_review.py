import logging

from fastapi import APIRouter, BackgroundTasks, Body, HTTPException, Query, Request, Response, status

from .. import config
from ..schemas import ai_portfolio_review as schemas_review
from ..schemas import async_task
from ..schemas.base_req_resp import BaseResponse
from ..services import msai_build_portfolio as services_construction
from ..services import msai_review_portfolio as services_review
from ..services import portfolio_verification
from . import async_task as router_async_task
from . import proxy_handler

router = APIRouter(prefix="/ai", tags=["ai"])

_TASK_TYPE = "analyze_portfolio"
_CONSTRUCTION_THRESHOLD = 0.35


def _routes_to_construction(request: schemas_review.AnalyzePortfolioRequest) -> bool:
    submitted_count = len(request.current_allocation)
    if submitted_count == 0:
        return True
    positive_count = sum(position.num_shares > 0 for position in request.current_allocation)
    return positive_count / submitted_count <= _CONSTRUCTION_THRESHOLD


async def _analyze(
    request: schemas_review.AnalyzePortfolioRequest,
) -> schemas_review.AnalyzePortfolioResponse:
    try:
        if _routes_to_construction(request):
            result = await services_construction.ai_build_portfolio(
                portfolio=request.current_allocation,
                country=request.country,
                investor_theme=request.investor_theme,
            )
        else:
            result = await services_review.ai_review_portfolio(
                portfolio=request.current_allocation,
                country=request.country,
                investor_theme=request.investor_theme,
                rebalance_plan=request.rebalance_plan,
            )
    except portfolio_verification.PortfolioInputError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except (
        portfolio_verification.PortfolioVerificationError,
        services_construction.PortfolioConstructionAIError,
        services_review.PortfolioReviewAIError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    return schemas_review.AnalyzePortfolioResponse(
        status=status.HTTP_200_OK,
        message="ok",
        data=result,
    )


@router.post(
    "/analyze_portfolio",
    response_model=schemas_review.AnalyzePortfolioResponse,
    response_model_exclude_none=True,
    responses={
        422: {
            "model": BaseResponse,
            "description": "The request, strategy, budget, or verified holdings are invalid.",
        },
        502: {
            "model": BaseResponse,
            "description": "Market verification, AI execution, or structured output failed.",
        },
    },
)
async def analyze_portfolio(
    http_request: Request,
    request: schemas_review.AnalyzePortfolioRequest = Body(description="The portfolio construction-or-review request."),
) -> schemas_review.AnalyzePortfolioResponse | Response:
    """Construct a sparse portfolio or return a structured review of an established portfolio."""

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
    request: schemas_review.AnalyzePortfolioRequest,
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
        logging.exception("Analyze portfolio task '%s' failed.", task_id)
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
    "/analyze_portfolio_async",
    response_model=schemas_review.AnalyzePortfolioAsyncResponse,
    response_model_exclude_none=True,
    responses={
        202: {
            "model": schemas_review.AnalyzePortfolioAsyncResponse,
            "description": "The portfolio-analysis task started or is still running.",
        },
        404: {"model": BaseResponse, "description": "The task was not found."},
        422: {
            "model": schemas_review.AnalyzePortfolioAsyncResponse | BaseResponse,
            "description": "The request, strategy, budget, or verified holdings are invalid.",
        },
        500: {
            "model": schemas_review.AnalyzePortfolioAsyncResponse | BaseResponse,
            "description": "The background task failed unexpectedly.",
        },
        502: {
            "model": schemas_review.AnalyzePortfolioAsyncResponse,
            "description": "Market verification, AI execution, or structured output failed.",
        },
    },
)
async def analyze_portfolio_async(
    background_tasks: BackgroundTasks,
    response: Response,
    http_request: Request,
    request: schemas_review.AnalyzePortfolioRequest | None = Body(
        None,
        description="The analyze portfolio request. Required when starting a task; omitted when polling.",
    ),
    task_id: str = Query("", description="Task ID returned by a previous call to this endpoint."),
) -> schemas_review.AnalyzePortfolioAsyncResponse | Response:
    """Start an analyze-portfolio task or poll a previously started task."""

    proxy_response = await proxy_handler.handle_if_proxy(
        config.settings_finhub_proxy.proxy_mode,
        config.settings_finhub_proxy.url_ai_task_node,
        http_request,
    )
    if proxy_response is not None:
        return proxy_response

    normalized_task_id = task_id.strip()
    if normalized_task_id:
        task_entry = await router_async_task.load_task(normalized_task_id, _TASK_TYPE)
        task_state = task_entry.state
        task_info = async_task.AsyncTaskInfo(task_id=normalized_task_id, state=task_state)
        if task_state == async_task.TASK_STATE_RUNNING:
            response.status_code = status.HTTP_202_ACCEPTED
            return schemas_review.AnalyzePortfolioAsyncResponse(
                status=status.HTTP_202_ACCEPTED,
                message="Task is running",
                extra=task_info,
            )
        if task_state == async_task.TASK_STATE_FAILED:
            failure_status = router_async_task.failure_status(task_entry)
            response.status_code = failure_status
            return schemas_review.AnalyzePortfolioAsyncResponse(
                status=failure_status,
                message=task_entry.message or "Task failed",
                extra=task_info,
            )

        result = schemas_review.AnalyzePortfolioResponse.model_validate(task_entry.result)
        return schemas_review.AnalyzePortfolioAsyncResponse(
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
        return await analyze_portfolio_async(
            background_tasks=background_tasks,
            response=response,
            http_request=http_request,
            request=request,
            task_id=new_task_id,
        )

    background_tasks.add_task(_run_task, new_task_id, request)
    response.status_code = status.HTTP_202_ACCEPTED
    return schemas_review.AnalyzePortfolioAsyncResponse(
        status=status.HTTP_202_ACCEPTED,
        message="Task started",
        extra=async_task.AsyncTaskInfo(
            task_id=new_task_id,
            state=async_task.TASK_STATE_RUNNING,
        ),
    )
