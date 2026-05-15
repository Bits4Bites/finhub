from typing import Literal

from fastapi import APIRouter, Query, Body, Header

from ..config import settings_llm, LLMTaskConfigOverride
from ..models import finhub as models
from ..schemas import ai as schemas_ai
from ..services import ai as ai_service

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
    result: dict[str, models.AIVendorInfo] = {}
    for v in settings_llm.llm_config.keys():
        v_name = v.upper()
        result[v_name] = models.AIVendorInfo(name=v_name, tier_models={})
        for t in settings_llm.llm_config[v].keys():
            t_name = t.upper()
            result[v_name].tier_models[t_name] = list(settings_llm.llm_config[v][t].models or [])

    return schemas_ai.AIVendorsResponse(status=200, message="ok", data=result)


@router.get(
    "/analyze_dividend_event",
    response_model=schemas_ai.AnalyzeDividendEventResponse,
    response_model_exclude_none=True,
)
async def analyse_dividend_event(
    symbol: str = Query(
        description="The stock symbol. Accept Yahoo Finance format (CBA.AX for Commonwealth Bank of Australia) or EXCHANGE:CODE format (NASDAQ:AAPL for Apple Inc.)."
    ),
    ex_date: str = Query(description="Ex-Dividend date in format YYYY-MM-DD"),
    div_amount: float = Query(description="The dividend amount as float number, without currency symbol (e.g. 1.23)"),
    use_ai_vendor: str = Header(
        alias="X-AI-Vendor",
        default=None,
        description="Specify the AI vendor to use for this task",
    ),
    use_ai_tier: str = Header(
        alias="X-AI-Tier",
        default=None,
        description="Specify the AI tier - free, lowcost, premium - to use for this task",
    ),
    use_ai_model: str = Header(
        alias="X-AI-Model",
        default=None,
        description="Specify the AI model to use for this task",
    ),
) -> schemas_ai.AnalyzeDividendEventResponse:
    """
    Analyzes a dividend event using AI assistance.
    """
    llm_config_override = None
    if use_ai_vendor and use_ai_tier and use_ai_model:
        llm_config_override = LLMTaskConfigOverride(
            vendor=use_ai_vendor.upper(),
            tier=use_ai_tier.upper(),
            model=use_ai_model,
        )
    result = await ai_service.ai_analyze_dividend_event(
        symbol=symbol,
        ex_date=ex_date,
        div_amount=div_amount,
        llm_config_override=llm_config_override,
    )
    if result is None:
        return schemas_ai.AnalyzeDividendEventResponse(status=400, message="Invalid inputs or stock not found")
    return schemas_ai.AnalyzeDividendEventResponse(status=200, message="ok", data=result)


@router.post(
    "/analyze_portfolio",
    response_model=schemas_ai.AnalyzePortfolioResponse,
    response_model_exclude_none=True,
)
async def analyze_portfolio(
    portfolio: schemas_ai.AnalyzePortfolioRequest = Body(
        description="The portfolio to analyze, including current tickers allocation and investor theme."
    ),
    template: Literal["allocation", "swing", "hybrid"] = Query(
        default="hybrid",
        description="Define which prompt template to use: 'allocation' for long-term growth, 'swing' for swing trading and 'hybrid' for both",
    ),
    use_ai_vendor: str = Header(
        alias="X-AI-Vendor",
        default=None,
        description="Specify the AI vendor to use for this task",
    ),
    use_ai_tier: str = Header(
        alias="X-AI-Tier",
        default=None,
        description="Specify the AI tier - free, lowcost, premium - to use for this task",
    ),
    use_ai_model: str = Header(
        alias="X-AI-Model",
        default=None,
        description="Specify the AI model to use for this task",
    ),
) -> schemas_ai.AnalyzePortfolioResponse:
    """
    Analyzes a portfolio using AI assistance.
    """
    llm_config_override = None
    if use_ai_vendor and use_ai_tier and use_ai_model:
        llm_config_override = LLMTaskConfigOverride(
            vendor=use_ai_vendor.upper(),
            tier=use_ai_tier.upper(),
            model=use_ai_model,
        )
    result = await ai_service.ai_analyze_portfolio(
        portfolio=portfolio.current_allocation,
        country=portfolio.country,
        investor_theme=portfolio.investor_theme or ai_service.DEFAULT_INVESTOR_THEME,
        template=template,
        llm_config_override=llm_config_override,
    )
    return schemas_ai.AnalyzePortfolioResponse(status=200, message="ok", data=result)
