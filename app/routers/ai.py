from fastapi import APIRouter, Query

from ..schemas import finhub as schemas
from ..services import ai as ai_service

router = APIRouter(prefix="/ai", tags=["ai"])


@router.get(
    "/analyze_dividend_event",
    response_model=schemas.AnalyzeDividendEventResponse,
    response_model_exclude_none=True,
)
async def analyse_dividend_event(
    symbol: str = Query(
        description="The stock symbol. Accept Yahoo Finance format (CBA.AX for Commonwealth Bank of Australia) or EXCHANGE:CODE format (NASDAQ:AAPL for Apple Inc.)."
    ),
    ex_date: str = Query(description="Ex-Dividend date in format YYYY-MM-DD"),
    div_amount: float = Query(description="The dividend amount as float number, without currency symbol (e.g. 1.23)"),
) -> schemas.AnalyzeDividendEventResponse:
    """
    Analyzes a dividend event.
    """
    result = await ai_service.ai_analyse_dividend_event(symbol=symbol, ex_date=ex_date, div_amount=div_amount)
    if result is None:
        return schemas.AnalyzeDividendEventResponse(status=400, message="Invalid inputs or stock not found")
    return schemas.AnalyzeDividendEventResponse(status=200, message="ok", data=result)
