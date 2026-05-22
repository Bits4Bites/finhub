from typing import Any, Optional

from pydantic import BaseModel

from .. import config
from ..models import finhub as models
from ..models.finhub import HistoryPoint


class BaseRequest(BaseModel):
    model_config = {"arbitrary_types_allowed": True}


class BaseResponse(BaseModel):
    status: int
    message: str
    data: Optional[Any] = None
    extra: Optional[Any] = None
    model_config = {"arbitrary_types_allowed": True}


class StockQuotesResponse(BaseResponse):
    data: Optional[dict[str, models.StockQuote]] = None


class StockQuoteResponse(BaseResponse):
    data: Optional[models.StockQuote] = None


class StockHistoryResponse(BaseResponse):
    data: Optional[list[HistoryPoint]] = None


class SymbolOverviewResponse(BaseResponse):
    data: Optional[models.SymbolOverview] = None


class SymbolInfoResponse(BaseResponse):
    data: Optional[models.SymbolInfo] = None


class StockQuoteAtDateResponse(BaseResponse):
    data: Optional[HistoryPoint] = None


class UpcomingEarningsResponse(BaseResponse):
    data: Optional[list[models.UpcomingEarningsEvent]] = None


class UpcomingDividendsResponse(BaseResponse):
    data: Optional[list[models.UpcomingDividendEvent]] = None


class ListingsResponse(BaseResponse):
    data: Optional[list[models.ListingEvent]] = None


class IndexCompaniesResponse(BaseResponse):
    data: Optional[list[config.CompanyBriefInfo]] = None
