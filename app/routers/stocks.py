from fastapi import APIRouter

from ..models.finhub import SymbolInfo
from ..schemas import finhub as schemas
from ..services import stock as stock_service

router = APIRouter(prefix="/stocks", tags=["stocks"])


@router.get("/quotes", response_model=schemas.StockQuotesResponse, response_model_exclude_none=True)
def get_stock_quotes(symbols: str = "") -> schemas.StockQuotesResponse:
    """
    Get stock quotes for a list of symbols.

    :param symbols: A comma-separated list of stock symbols to fetch quotes for.
    :type symbols: str
    :return: A StockQuotesResponse object containing the stock quotes for the requested symbols.
    :rtype: schemas.StockQuotesResponse
    """
    symbol_list = [symbol.strip() for symbol in symbols.split(",")]
    quotes = stock_service.get_stock_quotes(symbol_list)
    return schemas.StockQuotesResponse(status=200, message="ok", data=quotes)


@router.get("/{symbol}/info", response_model=schemas.BaseResponse, response_model_exclude_none=True)
def get_symbol_info(symbol: str):
    """
    Get detailed information for a given ticker symbol.
    """
    info = stock_service.get_symbol_info(symbol)
    # info.raw = stock_service.get_symbol_info_raw(symbol)
    return schemas.BaseResponse(status=200, message="ok", data=info)


@router.get("/{symbol}/info_debug", response_model=schemas.BaseResponse, response_model_exclude_none=True)
def get_symbol_info_debug(symbol: str):
    """
    Get detailed information for a given ticker symbol.
    """
    # info = stock_service.get_symbol_info(symbol)
    info = stock_service.get_symbol_info_raw(symbol)
    # info.raw = stock_service.get_symbol_info_raw(symbol)
    return schemas.BaseResponse(status=200, message="ok", data=info)
