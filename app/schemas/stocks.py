from ..models import market as models_market
from ..models import market_data as models_market_data
from ..models import stocks as models_stocks
from .base_req_resp import BaseResponse


class StockQuotesResponse(BaseResponse[dict[str, models_market_data.StockQuote]]):
    """Response envelope containing quotes keyed by requested symbol."""


class StockHistoryResponse(BaseResponse[list[models_market_data.HistoryPoint]]):
    """Response envelope containing historical price points."""


class SymbolOverviewResponse(BaseResponse[models_stocks.SymbolOverview]):
    """Response envelope containing company and security overview data."""


class SymbolInfoResponse(BaseResponse[models_stocks.SymbolInfo]):
    """Response envelope containing comprehensive symbol information."""


class StockQuoteAtDateResponse(BaseResponse[models_market_data.HistoryPoint]):
    """Response envelope containing a historical quote for one date."""


class IndexCompaniesResponse(BaseResponse[list[models_market.CompanyBriefInfo]]):
    """Response envelope containing constituents of a market index."""
