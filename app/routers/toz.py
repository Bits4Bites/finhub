from fastapi import APIRouter, Query

from ..schemas import finhub as schemas
from ..services import toz as toz_service

router = APIRouter(prefix="/toz", tags=["toz"])


@router.get("/gold/quote", response_model=schemas.StockQuoteResponse, response_model_exclude_none=True)
def get_gold_quote(
    currency: str = Query("USD", description="The currency code (e.g., 'USD', 'EUR') to get the price in."),
) -> schemas.StockQuoteResponse:
    """
    Get gold quote.
    """
    quote = toz_service.get_gold_quote(currency)
    return schemas.StockQuoteResponse(status=200, message="ok", data=quote)


@router.get("/gold/history", response_model=schemas.StockHistoryResponse, response_model_exclude_none=True)
def get_gold_history(
    currency: str = Query("USD", description="The currency code (e.g., 'USD', 'EUR') to get the price in."),
    days: int = Query(30, description="The number of days of historical data to retrieve."),
) -> schemas.StockHistoryResponse:
    """
    Get gold price history.
    """
    hist = toz_service.get_gold_history(currency, days)
    return schemas.StockHistoryResponse(status=200, message="ok", data=hist)


# ----------------------------------------------------------------------#


@router.get("/silver/quote", response_model=schemas.StockQuoteResponse, response_model_exclude_none=True)
def get_silver_quote(
    currency: str = Query("USD", description="The currency code (e.g., 'USD', 'EUR') to get the price in."),
) -> schemas.StockQuoteResponse:
    """
    Get silver quote.
    """
    quote = toz_service.get_silver_quote(currency)
    return schemas.StockQuoteResponse(status=200, message="ok", data=quote)


@router.get("/silver/history", response_model=schemas.StockHistoryResponse, response_model_exclude_none=True)
def get_silver_history(
    currency: str = Query("USD", description="The currency code (e.g., 'USD', 'EUR') to get the price in."),
    days: int = Query(30, description="The number of days of historical data to retrieve."),
) -> schemas.StockHistoryResponse:
    """
    Get silver price history.
    """
    hist = toz_service.get_silver_history(currency, days)
    return schemas.StockHistoryResponse(status=200, message="ok", data=hist)
