import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Body, HTTPException, Query, Response, status

from ..schemas import ai as schemas_ai
from ..schemas import async_task
from ..services import msai_analyze_div_event as service_analyze_div_event
from ..services import msai_analyze_ticker as service_analyze_ticker
from ..services import msai_build_portfolio as service_build_portfolio
from ..services import msai_review_portfolio as service_review_portfolio
from ..services import msai_spotlight_portfolio as service_spotlight_portfolio
from ..utils import cache

router = APIRouter(prefix="/ai", tags=["ai"])

_ANALYZE_DIVIDEND_EVENT_TASK_TYPE = "analyze_dividend_event"
_ANALYZE_TICKER_TASK_TYPE = "analyze_ticker"


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


async def _get_analyze_dividend_event_result(
    symbol: str,
    ex_date: str,
    div_amount: float,
    intent: str,
) -> schemas_ai.AnalyzeDividendEventResponse:
    result = await service_analyze_div_event.ai_analyze_div_event(
        symbol=symbol,
        ex_date=ex_date,
        div_amount=div_amount,
        intent=intent,
    )
    if result is None:
        return schemas_ai.AnalyzeDividendEventResponse(status=400, message="Invalid inputs or stock not found")
    return schemas_ai.AnalyzeDividendEventResponse(status=200, message="ok", data=result)


@router.get(
    "/analyze_dividend_event",
    response_model=schemas_ai.AnalyzeDividendEventResponse,
    response_model_exclude_none=True,
)
async def analyse_dividend_event(
    symbol: str = Query(
        description="The stock symbol. Accept Yahoo Finance format (e.g. CBA.AX) or EXCHANGE:CODE format (e.g. NASDAQ:AAPL)."
    ),
    ex_date: str = Query(description="Ex-Dividend date in format YYYY-MM-DD"),
    div_amount: float = Query(description="The dividend amount as float number, without currency symbol (e.g. 1.23)."),
    intent: str = Query(
        default=service_analyze_div_event.DEFAULT_INTENT,
        description="The intent to use for this analysis. It can be used to specify the context or goal of the analysis.",
    ),
) -> schemas_ai.AnalyzeDividendEventResponse:
    """
    Analyzes a dividend event using AI assistance.
    """
    return await _get_analyze_dividend_event_result(symbol, ex_date, div_amount, intent)


async def _run_analyze_dividend_event_task(
    task_id: str,
    symbol: str,
    ex_date: str,
    div_amount: float,
    intent: str,
) -> None:
    try:
        result = await _get_analyze_dividend_event_result(symbol, ex_date, div_amount, intent)
    except Exception:
        logging.exception("Analyze dividend event task '%s' failed.", task_id)
        await cache.set(
            task_id,
            {
                "task_type": _ANALYZE_DIVIDEND_EVENT_TASK_TYPE,
                "state": async_task.TASK_STATE_FAILED,
                "message": "Task failed",
            },
            ttl=async_task.ASYNC_TASK_TTL,
        )
        return

    await cache.set(
        task_id,
        {
            "task_type": _ANALYZE_DIVIDEND_EVENT_TASK_TYPE,
            "state": async_task.TASK_STATE_COMPLETED,
            "result": result.model_dump(mode="json"),
        },
        ttl=async_task.ASYNC_TASK_TTL,
    )


@router.get(
    "/analyze_dividend_event_async",
    response_model=schemas_ai.AnalyzeDividendEventAsyncResponse,
    response_model_exclude_none=True,
)
async def analyse_dividend_event_async(
    background_tasks: BackgroundTasks,
    response: Response,
    symbol: str = Query(
        "",
        description="The stock symbol. Required when starting a task; not required when polling.",
    ),
    ex_date: str = Query(
        "",
        description="Ex-dividend date in format YYYY-MM-DD. Required when starting a task; not required when polling.",
    ),
    div_amount: float | None = Query(
        None,
        description="The dividend amount as a float. Required when starting a task; not required when polling.",
    ),
    intent: str = Query(
        default=service_analyze_div_event.DEFAULT_INTENT,
        description="The intent to use for this analysis.",
    ),
    task_id: str = Query("", description="Task ID returned by a previous call to this endpoint."),
) -> schemas_ai.AnalyzeDividendEventAsyncResponse:
    """
    Start an analyze-dividend-event task or poll a previously started task.
    """
    task_id = task_id.strip()
    if task_id:
        task_entry = await cache.get(task_id)
        if not isinstance(task_entry, dict) or task_entry.get("task_type") != _ANALYZE_DIVIDEND_EVENT_TASK_TYPE:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

        task_state = task_entry.get("state")
        if task_state not in {
            async_task.TASK_STATE_RUNNING,
            async_task.TASK_STATE_COMPLETED,
            async_task.TASK_STATE_FAILED,
        }:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Invalid task state")

        task_info = schemas_ai.AsyncTaskInfo(task_id=task_id, state=task_state)
        if task_state == async_task.TASK_STATE_RUNNING:
            response.status_code = status.HTTP_202_ACCEPTED
            return schemas_ai.AnalyzeDividendEventAsyncResponse(
                status=status.HTTP_202_ACCEPTED,
                message="Task is running",
                extra=task_info,
            )
        if task_state == async_task.TASK_STATE_FAILED:
            response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
            return schemas_ai.AnalyzeDividendEventAsyncResponse(
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                message=task_entry.get("message", "Task failed"),
                extra=task_info,
            )
        if not isinstance(task_entry.get("result"), dict):
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Invalid task state")

        result = schemas_ai.AnalyzeDividendEventResponse.model_validate(task_entry["result"])
        return schemas_ai.AnalyzeDividendEventAsyncResponse(
            status=result.status,
            message=result.message,
            data=result.data,
            extra=task_info,
        )

    if not symbol.strip() or not ex_date.strip() or div_amount is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Symbol, ex_date and div_amount are required when starting a task",
        )

    task_id = str(uuid.uuid4())
    await cache.set(
        task_id,
        {
            "task_type": _ANALYZE_DIVIDEND_EVENT_TASK_TYPE,
            "state": async_task.TASK_STATE_RUNNING,
        },
        ttl=async_task.ASYNC_TASK_TTL,
    )
    background_tasks.add_task(
        _run_analyze_dividend_event_task,
        task_id,
        symbol,
        ex_date,
        div_amount,
        intent,
    )
    response.status_code = status.HTTP_202_ACCEPTED
    return schemas_ai.AnalyzeDividendEventAsyncResponse(
        status=status.HTTP_202_ACCEPTED,
        message="Task started",
        extra=schemas_ai.AsyncTaskInfo(task_id=task_id, state=async_task.TASK_STATE_RUNNING),
    )


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
        await cache.set(
            task_id,
            {
                "task_type": _ANALYZE_TICKER_TASK_TYPE,
                "state": async_task.TASK_STATE_FAILED,
                "message": "Task failed",
            },
            ttl=async_task.ASYNC_TASK_TTL,
        )
        return

    await cache.set(
        task_id,
        {
            "task_type": _ANALYZE_TICKER_TASK_TYPE,
            "state": async_task.TASK_STATE_COMPLETED,
            "result": result.model_dump(mode="json"),
        },
        ttl=async_task.ASYNC_TASK_TTL,
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
        task_entry = await cache.get(task_id)
        if not isinstance(task_entry, dict) or task_entry.get("task_type") != _ANALYZE_TICKER_TASK_TYPE:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

        task_state = task_entry.get("state")
        if task_state not in {
            async_task.TASK_STATE_RUNNING,
            async_task.TASK_STATE_COMPLETED,
            async_task.TASK_STATE_FAILED,
        }:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Invalid task state")

        task_info = schemas_ai.AsyncTaskInfo(task_id=task_id, state=task_state)
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
                message=task_entry.get("message", "Task failed"),
                extra=task_info,
            )
        if not isinstance(task_entry.get("result"), dict):
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Invalid task state")

        result = schemas_ai.AnalysisResponse.model_validate(task_entry["result"])
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

    task_id = str(uuid.uuid4())
    await cache.set(
        task_id,
        {
            "task_type": _ANALYZE_TICKER_TASK_TYPE,
            "state": async_task.TASK_STATE_RUNNING,
        },
        ttl=async_task.ASYNC_TASK_TTL,
    )
    background_tasks.add_task(_run_analyze_ticker_task, task_id, req.symbol, req.intent)
    response.status_code = status.HTTP_202_ACCEPTED
    return schemas_ai.AnalyzeTickerAsyncResponse(
        status=status.HTTP_202_ACCEPTED,
        message="Task started",
        extra=schemas_ai.AsyncTaskInfo(task_id=task_id, state=async_task.TASK_STATE_RUNNING),
    )


# ----------------------------------------------------------------------


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
    result = await service_build_portfolio.ai_build_portfolio(
        existing_positions=req.current_allocation,
        country=req.country,
        investor_theme=req.investor_theme,
    )
    if not result:
        return schemas_ai.ReviewPortfolioResponse(status=400, message="Invalid input or execution failed")
    return schemas_ai.ReviewPortfolioResponse(status=200, message="ok", data=result)


# ----------------------------------------------------------------------


@router.post(
    "/spotlight_portfolio",
    response_model=schemas_ai.AnalyzePortfolioResponse,
    response_model_exclude_none=True,
)
async def spotlight_portfolio(
    req: schemas_ai.AnalyzePortfolioRequest = Body(description="The spotlight portfolio request."),
) -> schemas_ai.AnalyzePortfolioResponse:
    """
    Reviews a portfolio and highlights immediate risks and actions using AI assistance.
    """
    result = await service_spotlight_portfolio.ai_spotlight_portfolio(
        portfolio=req.current_allocation,
        country=req.country,
        investor_theme=req.investor_theme,
    )
    if not result:
        return schemas_ai.AnalyzePortfolioResponse(status=400, message="Invalid input or execution failed")
    return schemas_ai.AnalyzePortfolioResponse(status=200, message="ok", data=result)


# ----------------------------------------------------------------------


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
    if req.current_allocation:
        result = await service_review_portfolio.ai_review_portfolio(
            portfolio=req.current_allocation,
            country=req.country,
            investor_theme=req.investor_theme,
            rebalance_plan=req.rebalance_plan,
        )
    else:
        result = await service_build_portfolio.ai_build_portfolio(
            existing_positions=None,
            country=req.country,
            investor_theme=req.investor_theme,
        )
    if not result:
        return schemas_ai.ReviewPortfolioResponse(status=400, message="Invalid input or execution failed")
    return schemas_ai.ReviewPortfolioResponse(status=200, message="ok", data=result)
