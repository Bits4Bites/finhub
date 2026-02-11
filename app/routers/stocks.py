from fastapi import APIRouter, Query, Path

from ..schemas import finhub as schemas
from ..services import stock as stock_service

router = APIRouter(prefix="/stocks")


@router.get("/quotes", response_model=schemas.StockQuotesResponse, response_model_exclude_none=True)
def get_stock_quotes(
    symbols: str = Query("", description="A comma-separated list of stock symbols to fetch quotes for."),
) -> schemas.StockQuotesResponse:
    """
    Get stock quotes for a list of symbols.
    """
    symbol_list = [symbol.strip() for symbol in symbols.split(",")]
    quotes = stock_service.get_stock_quotes(symbol_list)
    return schemas.StockQuotesResponse(status=200, message="ok", data=quotes)


@router.get("/{symbol}/info", response_model=schemas.SymbolInfoResponse, response_model_exclude_none=True)
def get_symbol_info(
    symbol: str = Path(description="The stock symbol to fetch information for."),
) -> schemas.SymbolInfoResponse:
    """
    Get detailed information for a given ticker symbol.
    """
    info = stock_service.get_symbol_info(symbol)
    return schemas.SymbolInfoResponse(status=200, message="ok", data=info)


@router.get("/{symbol}/info_debug", response_model=schemas.BaseResponse, response_model_exclude_none=True)
def get_symbol_info_debug(symbol: str):
    """
    Get detailed information for a given ticker symbol (debug mode).
    """
    info = stock_service.get_symbol_info_raw(symbol)
    return schemas.BaseResponse(status=200, message="ok", data=info)
