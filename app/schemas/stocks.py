from .. import config
from ..models import finhub as models
from .base_req_resp import BaseResponse


class StockQuotesResponse(BaseResponse[dict[str, models.StockQuote]]):
    pass


class StockQuoteResponse(BaseResponse[models.StockQuote]):
    pass


class StockHistoryResponse(BaseResponse[list[models.HistoryPoint]]):
    pass


class SymbolOverviewResponse(BaseResponse[models.SymbolOverview]):
    pass


class SymbolInfoResponse(BaseResponse[models.SymbolInfo]):
    pass


class StockQuoteAtDateResponse(BaseResponse[models.HistoryPoint]):
    pass


class IndexCompaniesResponse(BaseResponse[list[config.CompanyBriefInfo]]):
    pass
