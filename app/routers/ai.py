from fastapi import APIRouter, Body, Query

from ..schemas import ai as schemas_ai
from ..services import msai_analyze_div_event as service_analyze_div_event
from ..services import msai_analyze_ticker as service_analyze_ticker
from ..services import msai_build_portfolio as service_build_portfolio
from ..services import msai_review_portfolio as service_review_portfolio

router = APIRouter(prefix="/ai", tags=["ai"])


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
    result = await service_analyze_div_event.ai_analyze_div_event(
        symbol=symbol,
        ex_date=ex_date,
        div_amount=div_amount,
        intent=intent,
    )
    if result is None:
        return schemas_ai.AnalyzeDividendEventResponse(status=400, message="Invalid inputs or stock not found")
    return schemas_ai.AnalyzeDividendEventResponse(status=200, message="ok", data=result)


@router.post(
    "/analyze_ticker",
    response_model=schemas_ai.AnalysisResponse,
    response_model_exclude_none=True,
)
async def analyze_ticker(
    req: schemas_ai.AnalyzeTickerRequest = Body(description="The analyze request."),
) -> schemas_ai.AnalysisResponse:
    """
    Analyzes a ticker using AI assistance.
    """
    result = await service_analyze_ticker.ai_analyze_ticker(symbol=req.symbol, intent=req.intent)
    if not result:
        return schemas_ai.AnalysisResponse(status=400, message="Invalid stock symbol or analysis failed")
    return schemas_ai.AnalysisResponse(status=200, message="ok", data=result)


@router.post(
    "/build_portfolio",
    response_model=schemas_ai.AnalyzePortfolioResponse,
    response_model_exclude_none=True,
)
async def build_portfolio(
    req: schemas_ai.AnalyzePortfolioRequest = Body(description="The build portfolio request."),
) -> schemas_ai.AnalyzePortfolioResponse:
    """
    Builds a portfolio using AI assistance.
    """
    result = await service_build_portfolio.ai_build_portfolio(
        existing_positions=req.current_allocation,
        country=req.country,
        investor_theme=req.investor_theme,
    )
    if not result:
        return schemas_ai.AnalyzePortfolioResponse(status=400, message="Invalid input or execution failed")
    return schemas_ai.AnalyzePortfolioResponse(status=200, message="ok", data=result)


@router.post(
    "/analyze_portfolio",
    response_model=schemas_ai.AnalyzePortfolioResponse,
    response_model_exclude_none=True,
)
async def analyze_portfolio(
    req: schemas_ai.AnalyzePortfolioRequest = Body(description="The analyze portfolio request."),
) -> schemas_ai.AnalyzePortfolioResponse:
    """
    Analyzes a portfolio using AI assistance: review and give recommendations if current holding positions is supplied;
    otherwise build a new portfolio.
    """
    if req.current_allocation:
        result = await service_review_portfolio.ai_review_portfolio(
            portfolio=req.current_allocation,
            country=req.country,
            investor_theme=req.investor_theme,
        )
    else:
        result = await service_build_portfolio.ai_build_portfolio(
            existing_positions=None,
            country=req.country,
            investor_theme=req.investor_theme,
        )
    if not result:
        return schemas_ai.AnalyzePortfolioResponse(status=400, message="Invalid input or analysis failed")
    return schemas_ai.AnalyzePortfolioResponse(status=200, message="ok", data=result)
