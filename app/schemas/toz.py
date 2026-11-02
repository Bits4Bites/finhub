from ..models import market_data as models_market_data
from .base_req_resp import BaseResponse


class PreciousMetalQuoteResponse(BaseResponse[models_market_data.StockQuote]):
    """Response envelope containing one precious-metal quote."""


class PreciousMetalHistoryResponse(BaseResponse[list[models_market_data.HistoryPoint]]):
    """Response envelope containing precious-metal price history."""
