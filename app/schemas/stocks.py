from .. import config
from ..models import finhub as models
from .base_req_resp import BaseResponse


class StockQuotesResponse(BaseResponse[dict[str, models.StockQuote]]):
    """Response envelope containing quotes keyed by requested symbol."""


class StockQuoteResponse(BaseResponse[models.StockQuote]):
    """Response envelope containing one stock quote."""


class StockHistoryResponse(BaseResponse[list[models.HistoryPoint]]):
    """Response envelope containing historical price points."""


class SymbolOverviewResponse(BaseResponse[models.SymbolOverview]):
    """Response envelope containing company and security overview data."""


class SymbolInfoResponse(BaseResponse[models.SymbolInfo]):
    """Response envelope containing comprehensive symbol information."""


class StockQuoteAtDateResponse(BaseResponse[models.HistoryPoint]):
    """Response envelope containing a historical quote for one date."""


class IndexCompaniesResponse(BaseResponse[list[config.CompanyBriefInfo]]):
    """Response envelope containing constituents of a market index."""
