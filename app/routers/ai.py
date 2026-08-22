import logging

from fastapi import APIRouter, BackgroundTasks, Body, HTTPException, Query, Response, status

from ..schemas import ai as schemas_ai
from ..schemas import async_task
from ..services import msai_analyze_ticker as service_analyze_ticker
from ..services import msai_build_portfolio as service_build_portfolio
from ..services import msai_review_portfolio as service_review_portfolio
from . import async_task as router_async_task

router = APIRouter(prefix="/ai", tags=["ai"])

_ANALYZE_TICKER_TASK_TYPE = "analyze_ticker"
_BUILD_PORTFOLIO_TASK_TYPE = "build_portfolio"
_ANALYZE_PORTFOLIO_TASK_TYPE = "analyze_portfolio"


@router.get(
    "/vendors",
    response_model=schemas_ai.AIVendorsResponse,
    response_model_exclude_none=True,
)
async def get_vendors() -> schemas_ai.AIVendorsResponse:
    """
    Get the list of available AI vendors and supported API tiers and models.
    """
    from .. import config
    from ..models import ai as models_ai

    result: dict[str, models_ai.AIVendorInfo] = {}
    for v in config.settings_llm_vendor.vendors.keys():
        v_name = v.upper()
        result[v_name] = models_ai.AIVendorInfo(name=v_name, tier_models={})
        for t in config.settings_llm_vendor.vendors[v].keys():
            t_name = t.upper()
            result[v_name].tier_models[t_name] = list(config.settings_llm_vendor.vendors[v][t].models or [])

    return schemas_ai.AIVendorsResponse(status=200, message="ok", data=result)


# ----------------------------------------------------------------------


async def _get_analyze_ticker_result(symbol: str, intent: str) -> schemas_ai.AnalysisResponse:
    result = await service_analyze_ticker.ai_analyze_ticker(symbol=symbol, intent=intent)
    if not result:
        return schemas_ai.AnalysisResponse(status=400, message="Invalid stock symbol or analysis failed")
    return schemas_ai.AnalysisResponse(status=200, message="ok", data=result)


@router.post(
    "/analyze_ticker",
    response_model=schemas_ai.AnalysisResponse,
    response_model_exclude_none=True,
)
async def analyze_ticker(
    req: schemas_ai.AnalyzeTickerRequest = Body(description="The analyze portfolio request."),
) -> schemas_ai.AnalysisResponse:
    """
    Analyzes a ticker using AI assistance.
    """
    return await _get_analyze_ticker_result(req.symbol, req.intent)


async def _run_analyze_ticker_task(task_id: str, symbol: str, intent: str) -> None:
    try:
        result = await _get_analyze_ticker_result(symbol, intent)
    except Exception:
        logging.exception("Analyze ticker task '%s' failed.", task_id)
        await router_async_task.fail_task(task_id, _ANALYZE_TICKER_TASK_TYPE)
        return

    await router_async_task.complete_task(
        task_id,
        _ANALYZE_TICKER_TASK_TYPE,
        result,
    )


@router.post(
    "/analyze_ticker_async",
    response_model=schemas_ai.AnalyzeTickerAsyncResponse,
    response_model_exclude_none=True,
)
async def analyze_ticker_async(
    background_tasks: BackgroundTasks,
    response: Response,
    req: schemas_ai.AnalyzeTickerRequest | None = Body(
        None,
        description="The ticker analysis request. Required when starting a task; not required when polling.",
    ),
    task_id: str = Query("", description="Task ID returned by a previous call to this endpoint."),
) -> schemas_ai.AnalyzeTickerAsyncResponse:
    """
    Start an analyze-ticker task or poll a previously started task.
    """
    task_id = task_id.strip()
    if task_id:
        task_entry = await router_async_task.load_task(task_id, _ANALYZE_TICKER_TASK_TYPE)
        task_state = task_entry.state
        task_info = async_task.AsyncTaskInfo(task_id=task_id, state=task_state)
        if task_state == async_task.TASK_STATE_RUNNING:
            response.status_code = status.HTTP_202_ACCEPTED
            return schemas_ai.AnalyzeTickerAsyncResponse(
                status=status.HTTP_202_ACCEPTED,
                message="Task is running",
                extra=task_info,
            )
        if task_state == async_task.TASK_STATE_FAILED:
            response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
            return schemas_ai.AnalyzeTickerAsyncResponse(
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                message=task_entry.message or "Task failed",
                extra=task_info,
            )

        result = schemas_ai.AnalysisResponse.model_validate(task_entry.result)
        return schemas_ai.AnalyzeTickerAsyncResponse(
            status=result.status,
            message=result.message,
            data=result.data,
            extra=task_info,
        )

    if req is None or not req.symbol.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Symbol is required when starting a task",
        )

    task_id = await router_async_task.start_task(_ANALYZE_TICKER_TASK_TYPE)
    background_tasks.add_task(_run_analyze_ticker_task, task_id, req.symbol, req.intent)
    response.status_code = status.HTTP_202_ACCEPTED
    return schemas_ai.AnalyzeTickerAsyncResponse(
        status=status.HTTP_202_ACCEPTED,
        message="Task started",
        extra=async_task.AsyncTaskInfo(task_id=task_id, state=async_task.TASK_STATE_RUNNING),
    )


# ----------------------------------------------------------------------


async def _get_build_portfolio_result(
    req: schemas_ai.AnalyzePortfolioRequest,
) -> schemas_ai.ReviewPortfolioResponse:
    result = await service_build_portfolio.ai_build_portfolio(
        existing_positions=req.current_allocation,
        country=req.country,
        investor_theme=req.investor_theme,
    )
    if not result:
        return schemas_ai.ReviewPortfolioResponse(status=400, message="Invalid input or execution failed")
    return schemas_ai.ReviewPortfolioResponse(status=200, message="ok", data=result)


@router.post(
    "/build_portfolio",
    response_model=schemas_ai.ReviewPortfolioResponse,
    response_model_exclude_none=True,
)
async def build_portfolio(
    req: schemas_ai.AnalyzePortfolioRequest = Body(description="The build portfolio request."),
) -> schemas_ai.ReviewPortfolioResponse:
    """
    Builds a portfolio using AI assistance.
    """
    return await _get_build_portfolio_result(req)


async def _run_build_portfolio_task(
    task_id: str,
    req: schemas_ai.AnalyzePortfolioRequest,
) -> None:
    try:
        result = await _get_build_portfolio_result(req)
    except Exception:
        logging.exception("Build portfolio task '%s' failed.", task_id)
        await router_async_task.fail_task(task_id, _BUILD_PORTFOLIO_TASK_TYPE)
        return

    await router_async_task.complete_task(
        task_id,
        _BUILD_PORTFOLIO_TASK_TYPE,
        result,
    )


@router.post(
    "/build_portfolio_async",
    response_model=schemas_ai.BuildPortfolioAsyncResponse,
    response_model_exclude_none=True,
)
async def build_portfolio_async(
    background_tasks: BackgroundTasks,
    response: Response,
    req: schemas_ai.AnalyzePortfolioRequest | None = Body(
        None,
        description="The build portfolio request. Required when starting a task; not required when polling.",
    ),
    task_id: str = Query("", description="Task ID returned by a previous call to this endpoint."),
) -> schemas_ai.BuildPortfolioAsyncResponse:
    """
    Start a build-portfolio task or poll a previously started task.
    """
    task_id = task_id.strip()
    if task_id:
        task_entry = await router_async_task.load_task(task_id, _BUILD_PORTFOLIO_TASK_TYPE)
        task_state = task_entry.state
        task_info = async_task.AsyncTaskInfo(task_id=task_id, state=task_state)
        if task_state == async_task.TASK_STATE_RUNNING:
            response.status_code = status.HTTP_202_ACCEPTED
            return schemas_ai.BuildPortfolioAsyncResponse(
                status=status.HTTP_202_ACCEPTED,
                message="Task is running",
                extra=task_info,
            )
        if task_state == async_task.TASK_STATE_FAILED:
            response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
            return schemas_ai.BuildPortfolioAsyncResponse(
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                message=task_entry.message or "Task failed",
                extra=task_info,
            )

        result = schemas_ai.ReviewPortfolioResponse.model_validate(task_entry.result)
        return schemas_ai.BuildPortfolioAsyncResponse(
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

    task_id = await router_async_task.start_task(_BUILD_PORTFOLIO_TASK_TYPE)
    background_tasks.add_task(_run_build_portfolio_task, task_id, req)
    response.status_code = status.HTTP_202_ACCEPTED
    return schemas_ai.BuildPortfolioAsyncResponse(
        status=status.HTTP_202_ACCEPTED,
        message="Task started",
        extra=async_task.AsyncTaskInfo(task_id=task_id, state=async_task.TASK_STATE_RUNNING),
    )


# ----------------------------------------------------------------------


async def _get_analyze_portfolio_result(
    req: schemas_ai.AnalyzePortfolioRequest,
) -> schemas_ai.ReviewPortfolioResponse:
    has_no_holdings = not req.current_allocation or all(pos.num_shares == 0 for pos in req.current_allocation)
    if has_no_holdings:
        result = await service_build_portfolio.ai_build_portfolio(
            existing_positions=None,
            country=req.country,
            investor_theme=req.investor_theme,
        )
    else:
        result = await service_review_portfolio.ai_review_portfolio(
            portfolio=req.current_allocation,
            country=req.country,
            investor_theme=req.investor_theme,
            rebalance_plan=req.rebalance_plan,
        )
    if not result:
        return schemas_ai.ReviewPortfolioResponse(status=400, message="Invalid input or execution failed")
    return schemas_ai.ReviewPortfolioResponse(status=200, message="ok", data=result)


@router.post(
    "/analyze_portfolio",
    response_model=schemas_ai.ReviewPortfolioResponse,
    response_model_exclude_none=True,
)
async def analyze_portfolio(
    req: schemas_ai.AnalyzePortfolioRequest = Body(description="The analyze portfolio request."),
) -> schemas_ai.ReviewPortfolioResponse:
    """
    Analyzes a portfolio using AI assistance: review and give recommendations if current holding positions is supplied;
    otherwise build a new portfolio.
    """
    return await _get_analyze_portfolio_result(req)


async def _run_analyze_portfolio_task(
    task_id: str,
    req: schemas_ai.AnalyzePortfolioRequest,
) -> None:
    try:
        result = await _get_analyze_portfolio_result(req)
    except Exception:
        logging.exception("Analyze portfolio task '%s' failed.", task_id)
        await router_async_task.fail_task(task_id, _ANALYZE_PORTFOLIO_TASK_TYPE)
        return

    await router_async_task.complete_task(
        task_id,
        _ANALYZE_PORTFOLIO_TASK_TYPE,
        result,
    )


@router.post(
    "/analyze_portfolio_async",
    response_model=schemas_ai.AnalyzePortfolioAsyncResponse,
    response_model_exclude_none=True,
)
async def analyze_portfolio_async(
    background_tasks: BackgroundTasks,
    response: Response,
    req: schemas_ai.AnalyzePortfolioRequest | None = Body(
        None,
        description="The analyze portfolio request. Required when starting a task; not required when polling.",
    ),
    task_id: str = Query("", description="Task ID returned by a previous call to this endpoint."),
) -> schemas_ai.AnalyzePortfolioAsyncResponse:
    """
    Start an analyze-portfolio task or poll a previously started task.
    """
    task_id = task_id.strip()
    if task_id:
        task_entry = await router_async_task.load_task(task_id, _ANALYZE_PORTFOLIO_TASK_TYPE)
        task_state = task_entry.state
        task_info = async_task.AsyncTaskInfo(task_id=task_id, state=task_state)
        if task_state == async_task.TASK_STATE_RUNNING:
            response.status_code = status.HTTP_202_ACCEPTED
            return schemas_ai.AnalyzePortfolioAsyncResponse(
                status=status.HTTP_202_ACCEPTED,
                message="Task is running",
                extra=task_info,
            )
        if task_state == async_task.TASK_STATE_FAILED:
            response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
            return schemas_ai.AnalyzePortfolioAsyncResponse(
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                message=task_entry.message or "Task failed",
                extra=task_info,
            )

        result = schemas_ai.ReviewPortfolioResponse.model_validate(task_entry.result)
        return schemas_ai.AnalyzePortfolioAsyncResponse(
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

    task_id = await router_async_task.start_task(_ANALYZE_PORTFOLIO_TASK_TYPE)
    background_tasks.add_task(_run_analyze_portfolio_task, task_id, req)
    response.status_code = status.HTTP_202_ACCEPTED
    return schemas_ai.AnalyzePortfolioAsyncResponse(
        status=status.HTTP_202_ACCEPTED,
        message="Task started",
        extra=async_task.AsyncTaskInfo(task_id=task_id, state=async_task.TASK_STATE_RUNNING),
    )
