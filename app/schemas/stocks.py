from .. import config
from ..models import finhub as models
from .base_req_resp import BaseResponse


class StockQuotesResponse(BaseResponse):
    data: dict[str, models.StockQuote] | None = None


class StockQuoteResponse(BaseResponse):
    data: models.StockQuote | None = None


class StockHistoryResponse(BaseResponse):
    data: list[models.HistoryPoint] | None = None


class SymbolOverviewResponse(BaseResponse):
    data: models.SymbolOverview | None = None


class SymbolInfoResponse(BaseResponse):
    data: models.SymbolInfo | None = None


class StockQuoteAtDateResponse(BaseResponse):
    data: models.HistoryPoint | None = None


class IndexCompaniesResponse(BaseResponse):
    data: list[config.CompanyBriefInfo] | None = None
