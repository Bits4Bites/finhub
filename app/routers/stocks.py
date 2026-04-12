from fastapi import APIRouter, Query, Path

from .. import config
from ..schemas import finhub as schemas
from ..services import stock as stock_service

router = APIRouter(prefix="/stocks", tags=["stocks"])


@router.get("/quotes", response_model=schemas.StockQuotesResponse, response_model_exclude_none=True)
def get_stock_quotes(
    symbols: str = Query(
        description="A comma-separated list of stock symbols to fetch quotes for, accepting YF format (e.g. ABC.AX) or EXCHANGE:CODE (e.g. NASDAQ:XYZ)"
    ),
) -> schemas.StockQuotesResponse:
    """
    Gets stock quotes for a list of symbols.
    """
    symbol_list = [symbol.strip() for symbol in symbols.upper().split(",")]
    quotes = stock_service.get_stock_quotes(symbol_list)
    return schemas.StockQuotesResponse(status=200, message="ok", data=quotes)


@router.get("/{symbol}/overview", response_model=schemas.SymbolOverviewResponse, response_model_exclude_none=True)
def get_symbol_overview(
    symbol: str = Path(
        description="The stock symbol to fetch information for, accepting YF format (e.g. ABC.AX) or EXCHANGE:CODE (e.g. NASDAQ:XYZ)"
    ),
) -> schemas.SymbolOverviewResponse:
    """
    Gets overview information for a given ticker symbol.
    """
    overview = stock_service.get_symbol_overview(symbol)
    if overview is None:
        return schemas.SymbolOverviewResponse(status=404, message="Symbol not found")
    return schemas.SymbolOverviewResponse(status=200, message="ok", data=overview)


@router.get("/{symbol}/info", response_model=schemas.SymbolInfoResponse, response_model_exclude_none=True)
def get_symbol_info(
    symbol: str = Path(
        description="The stock symbol to fetch information for, accepting YF format (e.g. ABC.AX) or EXCHANGE:CODE (e.g. NASDAQ:XYZ)"
    ),
) -> schemas.SymbolInfoResponse:
    """
    Gets detailed information for a given ticker symbol.
    """
    info = stock_service.get_symbol_info(symbol)
    if info is None:
        return schemas.SymbolInfoResponse(status=404, message="Symbol not found")
    return schemas.SymbolInfoResponse(status=200, message="ok", data=info)


@router.get(
    "/{symbol}/quote_at/{date_str}", response_model=schemas.StockQuoteAtDateResponse, response_model_exclude_none=True
)
def get_symbol_quote_at_date(
    symbol: str = Path(
        description="The stock symbol to fetch information for, accepting YF format (e.g. ABC.AX) or EXCHANGE:CODE (e.g. NASDAQ:XYZ)"
    ),
    date_str: str = Path(description="The date to fetch the quote for (format: YYYY-MM-DD)."),
) -> schemas.StockQuoteAtDateResponse:
    """
    Gets stock quote information for a given ticker symbol at a specific date.
    Note: If the date falls on a non-trading day, the API may return quote for the most recent trading day before the given date.
    """
    quote = stock_service.get_stock_quote_at_date(symbol, date_str)
    if quote is None:
        return schemas.StockQuoteAtDateResponse(status=404, message="Symbol or quote not found")
    return schemas.StockQuoteAtDateResponse(status=200, message="ok", data=quote)


@router.get("/{symbol}/info_debug", response_model=schemas.BaseResponse, response_model_exclude_none=True)
def get_symbol_info_debug(symbol: str):
    """
    Gets detailed information for a given ticker symbol (debug mode).
    """
    info = stock_service.get_symbol_info_raw(symbol)
    return schemas.BaseResponse(status=200, message="ok", data=info)


@router.get("/index/{index}/companies", response_model=schemas.IndexCompaniesResponse, response_model_exclude_none=True)
def get_index_companies(
    index: str = Path(description="The index to fetch companies for."),
) -> schemas.IndexCompaniesResponse:
    """
    Gets list of companies for a given index.
    Note: current supported indices are ASX20, ASX50, ASX100, ASX200, ASX300, NASDAQ100, SP500, SP400, SP600, VN30, VN100 and HNX30.
    """
    companies = []
    index = index.upper()
    if index in config.market_indices.indices:
        companies = config.market_indices.indices[index].values()
    return schemas.IndexCompaniesResponse(status=200, message="ok", data=companies)
