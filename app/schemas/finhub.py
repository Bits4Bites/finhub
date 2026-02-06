from pydantic import BaseModel
from typing import Optional, Any


class BaseResponse(BaseModel):
    status: int
    message: str
    data: Optional[Any] = None

    model_config = {"arbitrary_types_allowed": True}


class StockQuotesResponse(BaseResponse):
    data: Optional[dict[str, Any]] = None
