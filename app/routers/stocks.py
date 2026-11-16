import datetime

from fastapi import APIRouter, HTTPException, Path, Query, status

from ..schemas import stocks as schemas
from ..services import market as market_service
from ..services import stock as stock_service

router = APIRouter(prefix="/stocks", tags=["stocks"])


@router.get("/quotes", response_model=schemas.StockQuotesResponse, response_model_exclude_none=True)
def get_stock_quotes(
    symbols: str = Query(
        description="A comma-separated list of stock symbols to fetch quotes for, accepting YF format (e.g. ABC.AX) or EXCHANGE:CODE (e.g. NASDAQ:XYZ)"
    ),
) -> schemas.StockQuotesResponse:
    """Return current quotes for a caller-supplied symbol list.

    Args:
        symbols: Comma-separated Yahoo or ``EXCHANGE:CODE`` symbols. Entries
            are trimmed, uppercased, and deduplicated in first-seen order.

    Returns:
        An HTTP 200 response envelope with application status 200 and quotes
        keyed by normalized symbol. Symbols omitted by the data provider are
        absent from ``data``; no matches produce an empty object.

    Raises:
        HTTPException: HTTP 422 when the list is blank or contains an empty
            comma-separated entry.

    Notes:
        Missing query input returns HTTP 422 before provider lookup. Provider,
        conversion, and response-validation failures surface as HTTP 500 error
        responses.
    """
    symbol_list = []
    seen_symbols = set()
    for symbol in symbols.split(","):
        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="symbols must be a comma-separated list of non-empty stock symbols",
            )
        if normalized_symbol not in seen_symbols:
            seen_symbols.add(normalized_symbol)
            symbol_list.append(normalized_symbol)

    quotes = stock_service.get_stock_quotes(symbol_list)
    return schemas.StockQuotesResponse(status=200, message="ok", data=quotes)


@router.get("/{symbol}/overview", response_model=schemas.SymbolOverviewResponse, response_model_exclude_none=True)
def get_symbol_overview(
    symbol: str = Path(
        description="The stock symbol to fetch information for, accepting YF format (e.g. ABC.AX) or EXCHANGE:CODE (e.g. NASDAQ:XYZ)"
    ),
) -> schemas.SymbolOverviewResponse:
    """Return a summary of a supported financial security.

    Args:
        symbol: Yahoo or ``EXCHANGE:CODE`` symbol. It is trimmed and
            uppercased before lookup.

    Returns:
        An HTTP 200 response envelope. A found security uses application
        status 200 and includes its overview; an unsupported or missing
        security uses application status 404 and omits ``data``.

    Notes:
        The application-level 404 does not change the HTTP status from 200.
        Provider, conversion, and response-validation failures surface as
        HTTP 500 error responses.
    """
    overview = stock_service.get_symbol_overview(symbol.strip().upper())
    if overview is None:
        return schemas.SymbolOverviewResponse(status=404, message="Symbol not found")
    return schemas.SymbolOverviewResponse(status=200, message="ok", data=overview)


@router.get("/{symbol}/info", response_model=schemas.SymbolInfoResponse, response_model_exclude_none=True)
def get_symbol_info(
    symbol: str = Path(
        description="The stock symbol to fetch information for, accepting YF format (e.g. ABC.AX) or EXCHANGE:CODE (e.g. NASDAQ:XYZ)"
    ),
) -> schemas.SymbolInfoResponse:
    """Return detailed information for a supported financial security.

    Args:
        symbol: Yahoo or ``EXCHANGE:CODE`` symbol. It is trimmed and
            uppercased before lookup.

    Returns:
        An HTTP 200 response envelope. A found security uses application
        status 200 and includes detailed information; an unsupported or
        missing security uses application status 404 and omits ``data``.

    Notes:
        The application-level 404 does not change the HTTP status from 200.
        Provider, conversion, and response-validation failures surface as
        HTTP 500 error responses.
    """
    info = stock_service.get_symbol_info(symbol.strip().upper())
    if info is None:
        return schemas.SymbolInfoResponse(status=404, message="Symbol not found")
    return schemas.SymbolInfoResponse(status=200, message="ok", data=info)


@router.get("/{symbol}/history", response_model=schemas.StockHistoryResponse, response_model_exclude_none=True)
def get_symbol_history(
    symbol: str = Path(
        description="The stock symbol to fetch information for, accepting YF format (e.g. ABC.AX) or EXCHANGE:CODE (e.g. NASDAQ:XYZ)"
    ),
    days: int = Query(100, description="The number of days of historical data to retrieve."),
) -> schemas.StockHistoryResponse:
    """Return recent daily price history for a financial security.

    Args:
        symbol: Yahoo or ``EXCHANGE:CODE`` symbol. It is trimmed and
            uppercased before lookup.
        days: Requested history length. The default is 100; zero and negative
            values also use 100.

    Returns:
        An HTTP 200 response envelope with application status 200. Available
        observations remain in provider order, an available but empty history
        is returned as an empty list, and an unsupported symbol omits
        ``data``.

    Notes:
        A non-integer ``days`` value returns HTTP 422 before provider lookup.
        Provider, conversion, and response-validation failures surface as HTTP
        500 error responses.
    """
    normalized_days = 100 if days <= 0 else days
    hist = stock_service.get_symbol_history(symbol.strip().upper(), normalized_days)
    return schemas.StockHistoryResponse(status=200, message="ok", data=hist)


@router.get(
    "/{symbol}/quote_at/{date_str}", response_model=schemas.StockQuoteAtDateResponse, response_model_exclude_none=True
)
def get_symbol_quote_at_date(
    symbol: str = Path(
        description="The stock symbol to fetch information for, accepting YF format (e.g. ABC.AX) or EXCHANGE:CODE (e.g. NASDAQ:XYZ)"
    ),
    date_str: str = Path(description="The date to fetch the quote for (format: YYYY-MM-DD)."),
) -> schemas.StockQuoteAtDateResponse:
    """Return the latest daily quote on or before a requested date.

    Args:
        symbol: Yahoo or ``EXCHANGE:CODE`` symbol. It is trimmed and
            uppercased before lookup.
        date_str: Valid calendar date in fixed-width ``YYYY-MM-DD`` form.

    Returns:
        An HTTP 200 response envelope. A found quote uses application status
        200; no eligible quote or unsupported symbol uses application status
        404 and omits ``data``.

    Raises:
        HTTPException: HTTP 422 when ``date_str`` is malformed, not a calendar
            date, or not zero-padded to the documented width.

    Notes:
        The application-level 404 does not change the HTTP status from 200. A
        non-trading date may return the most recent quote within the preceding
        14 calendar days. Provider, conversion, and response-validation
        failures surface as HTTP 500 error responses.
    """
    try:
        if datetime.date.fromisoformat(date_str).isoformat() != date_str:
            raise ValueError
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="date must be a valid date in YYYY-MM-DD format",
        ) from exc

    quote = stock_service.get_stock_quote_at_date(symbol.strip().upper(), date_str)
    if quote is None:
        return schemas.StockQuoteAtDateResponse(status=404, message="Symbol or quote not found")
    return schemas.StockQuoteAtDateResponse(status=200, message="ok", data=quote)


@router.get("/{symbol}/info_debug", response_model=schemas.BaseResponse, response_model_exclude_none=True)
def get_symbol_info_debug(
    symbol: str = Path(description="The stock symbol to inspect, accepting YF format or EXCHANGE:CODE format."),
) -> schemas.BaseResponse:
    """Return raw provider metadata for debugging a symbol lookup.

    Args:
        symbol: Yahoo or ``EXCHANGE:CODE`` symbol. It is trimmed and
            uppercased before lookup.

    Returns:
        An HTTP 200 response envelope with application status 200 and the raw
        metadata object. An empty object is preserved; a null result omits
        ``data``.

    Notes:
        Provider and response-serialization failures surface as HTTP 500 error
        responses.
    """
    info = stock_service.get_symbol_info_raw(symbol.strip().upper())
    return schemas.BaseResponse(status=200, message="ok", data=info)


@router.get("/index/{index}/companies", response_model=schemas.IndexCompaniesResponse, response_model_exclude_none=True)
def get_index_companies(
    index: str = Path(description="The index to fetch companies for."),
) -> schemas.IndexCompaniesResponse:
    """Return available constituents for a market index.

    Args:
        index: Case-insensitive index identifier. Supported caches include
            ASX20, ASX50, ASX100, ASX200, ASX300, HNX30, NASDAQ100, SP400,
            SP500, SP600, VN30, and VN100.

    Returns:
        An HTTP 200 response envelope with application status 200. Available
        companies retain their published order. A supported index with no
        constituents and an unknown index both return an empty list.

    Notes:
        The identifier is trimmed and normalized to uppercase. Unknown indexes
        do not produce an HTTP or application-level 404.
    """
    normalized_index = index.strip().upper()
    companies = []
    if normalized_index in market_service.market_indices.indices:
        companies = list(market_service.market_indices.indices[normalized_index].values())
    return schemas.IndexCompaniesResponse(status=200, message="ok", data=companies)
