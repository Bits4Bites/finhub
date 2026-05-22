from .. import config
from ..models import finhub as models
from ..models.finhub import HistoryPoint
from .base_req_resp import BaseResponse


class StockQuotesResponse(BaseResponse):
    data: dict[str, models.StockQuote] | None = None


class StockQuoteResponse(BaseResponse):
    data: models.StockQuote | None = None


class StockHistoryResponse(BaseResponse):
    data: list[HistoryPoint] | None = None


class SymbolOverviewResponse(BaseResponse):
    data: models.SymbolOverview | None = None


class SymbolInfoResponse(BaseResponse):
    data: models.SymbolInfo | None = None


class StockQuoteAtDateResponse(BaseResponse):
    data: HistoryPoint | None = None


class UpcomingEarningsResponse(BaseResponse):
    data: list[models.UpcomingEarningsEvent] | None = None


class UpcomingDividendsResponse(BaseResponse):
    data: list[models.UpcomingDividendEvent] | None = None


class ListingsResponse(BaseResponse):
    data: list[models.ListingEvent] | None = None


class IndexCompaniesResponse(BaseResponse):
    data: list[config.CompanyBriefInfo] | None = None
