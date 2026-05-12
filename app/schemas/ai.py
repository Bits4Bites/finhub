from typing import Optional, List

from .finhub import BaseResponse, BaseRequest
from ..models import finhub as models
from ..services import ai as ai_services


class AnalyzeDividendEventResponse(BaseResponse):
    data: Optional[models.DividendEventAnalysis] = None


class AnalyzePortfolioRequest(BaseRequest):
    current_allocation: List[models.HoldingTicker] = []
    country: str = ""
    investor_theme: Optional[str] = ai_services.DEFAULT_INVESTOR_THEME


class AnalyzePortfolioResponse(BaseResponse):
    analysis: str = ""
