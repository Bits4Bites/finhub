from pydantic import BaseModel
from typing import Optional, Any
from ..models import finhub as models


class BaseResponse(BaseModel):
    status: int
    message: str
    data: Optional[Any] = None
    model_config = {"arbitrary_types_allowed": True}


class StockQuotesResponse(BaseResponse):
    data: Optional[dict[str, models.StockQuote]] = None
