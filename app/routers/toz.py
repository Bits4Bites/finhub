from fastapi import APIRouter, Query

from ..schemas import toz as schemas_toz
from ..services import toz as toz_service

router = APIRouter(prefix="/toz", tags=["toz"])


@router.get("/gold/quote", response_model=schemas_toz.PreciousMetalQuoteResponse, response_model_exclude_none=True)
def get_gold_quote(
    currency: str = Query("USD", description="The currency code (e.g., 'USD', 'EUR') to get the price in."),
) -> schemas_toz.PreciousMetalQuoteResponse:
    """
    Get gold quote.
    """
    quote = toz_service.get_gold_quote(currency)
    return schemas_toz.PreciousMetalQuoteResponse(status=200, message="ok", data=quote)


@router.get(
    "/gold/history",
    response_model=schemas_toz.PreciousMetalHistoryResponse,
    response_model_exclude_none=True,
)
def get_gold_history(
    currency: str = Query("USD", description="The currency code (e.g., 'USD', 'EUR') to get the price in."),
    days: int = Query(30, description="The number of days of historical data to retrieve."),
) -> schemas_toz.PreciousMetalHistoryResponse:
    """
    Get gold price history.
    """
    hist = toz_service.get_gold_history(currency, days)
    return schemas_toz.PreciousMetalHistoryResponse(status=200, message="ok", data=hist)


# ----------------------------------------------------------------------#


@router.get("/silver/quote", response_model=schemas_toz.PreciousMetalQuoteResponse, response_model_exclude_none=True)
def get_silver_quote(
    currency: str = Query("USD", description="The currency code (e.g., 'USD', 'EUR') to get the price in."),
) -> schemas_toz.PreciousMetalQuoteResponse:
    """
    Get silver quote.
    """
    quote = toz_service.get_silver_quote(currency)
    return schemas_toz.PreciousMetalQuoteResponse(status=200, message="ok", data=quote)


@router.get(
    "/silver/history",
    response_model=schemas_toz.PreciousMetalHistoryResponse,
    response_model_exclude_none=True,
)
def get_silver_history(
    currency: str = Query("USD", description="The currency code (e.g., 'USD', 'EUR') to get the price in."),
    days: int = Query(30, description="The number of days of historical data to retrieve."),
) -> schemas_toz.PreciousMetalHistoryResponse:
    """
    Get silver price history.
    """
    hist = toz_service.get_silver_history(currency, days)
    return schemas_toz.PreciousMetalHistoryResponse(status=200, message="ok", data=hist)
