from fastapi import APIRouter, Query

from ..schemas import toz as schemas_toz
from ..services import toz as toz_service

router = APIRouter(prefix="/toz", tags=["toz"])


def _normalize_currency(currency: str) -> str:
    return currency.strip().upper() or "USD"


@router.get("/gold/quote", response_model=schemas_toz.PreciousMetalQuoteResponse, response_model_exclude_none=True)
def get_gold_quote(
    currency: str = Query("USD", description="The currency code (e.g., 'USD', 'EUR') to get the price in."),
) -> schemas_toz.PreciousMetalQuoteResponse:
    """Return the current gold-futures quote in a requested currency.

    Args:
        currency: Case-insensitive target currency code. Surrounding
            whitespace is ignored; an omitted or blank value uses USD.

    Returns:
        An HTTP 200 response envelope with application status 200. ``data``
        contains the quote when the currency is supported and is omitted when
        no quote is available.

    Notes:
        Provider, currency-conversion, and response-validation failures
        surface as HTTP 500 error responses.
    """
    quote = toz_service.get_gold_quote(_normalize_currency(currency))
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
    """Return recent daily gold-futures history in a requested currency.

    Args:
        currency: Case-insensitive target currency code. Surrounding
            whitespace is ignored; an omitted or blank value uses USD.
        days: Requested history length. The default is 30; zero and negative
            values also use 30.

    Returns:
        An HTTP 200 response envelope with application status 200. Available
        observations remain in provider order, an available but empty history
        is returned as an empty list, and an unavailable currency omits
        ``data``.

    Notes:
        A non-integer ``days`` value returns HTTP 422 before provider lookup.
        Provider, currency-conversion, and response-validation failures
        surface as HTTP 500 error responses.
    """
    normalized_days = 30 if days <= 0 else days
    hist = toz_service.get_gold_history(_normalize_currency(currency), normalized_days)
    return schemas_toz.PreciousMetalHistoryResponse(status=200, message="ok", data=hist)


# ----------------------------------------------------------------------#


@router.get("/silver/quote", response_model=schemas_toz.PreciousMetalQuoteResponse, response_model_exclude_none=True)
def get_silver_quote(
    currency: str = Query("USD", description="The currency code (e.g., 'USD', 'EUR') to get the price in."),
) -> schemas_toz.PreciousMetalQuoteResponse:
    """Return the current silver-futures quote in a requested currency.

    Args:
        currency: Case-insensitive target currency code. Surrounding
            whitespace is ignored; an omitted or blank value uses USD.

    Returns:
        An HTTP 200 response envelope with application status 200. ``data``
        contains the quote when the currency is supported and is omitted when
        no quote is available.

    Notes:
        Provider, currency-conversion, and response-validation failures
        surface as HTTP 500 error responses.
    """
    quote = toz_service.get_silver_quote(_normalize_currency(currency))
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
    """Return recent daily silver-futures history in a requested currency.

    Args:
        currency: Case-insensitive target currency code. Surrounding
            whitespace is ignored; an omitted or blank value uses USD.
        days: Requested history length. The default is 30; zero and negative
            values also use 30.

    Returns:
        An HTTP 200 response envelope with application status 200. Available
        observations remain in provider order, an available but empty history
        is returned as an empty list, and an unavailable currency omits
        ``data``.

    Notes:
        A non-integer ``days`` value returns HTTP 422 before provider lookup.
        Provider, currency-conversion, and response-validation failures
        surface as HTTP 500 error responses.
    """
    normalized_days = 30 if days <= 0 else days
    hist = toz_service.get_silver_history(_normalize_currency(currency), normalized_days)
    return schemas_toz.PreciousMetalHistoryResponse(status=200, message="ok", data=hist)
