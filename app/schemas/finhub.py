from pydantic import BaseModel
from typing import Optional, Any
from ..models import finhub as models


class BaseResponse(BaseModel):
    status: int
    message: str
    data: Optional[Any] = None
    extra: Optional[Any] = None
    model_config = {"arbitrary_types_allowed": True}


class StockQuotesResponse(BaseResponse):
    data: Optional[dict[str, models.StockQuote]] = None


class SymbolOverviewResponse(BaseResponse):
    data: Optional[models.SymbolOverview] = None


class SymbolInfoResponse(BaseResponse):
    data: Optional[models.SymbolInfo] = None


class IncomingEarningsResponse(BaseResponse):
    data: Optional[list[models.IncomingEarningsEvent]] = None


class IncomingDividendsResponse(BaseResponse):
    data: Optional[list[models.IncomingDividendEvent]] = None
