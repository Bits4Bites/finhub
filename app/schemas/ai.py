from pydantic import Field

from ..models import ai as models_ai
from ..services import msai_analyze_ticker as service_analyze_ticker
from . import async_task
from .base_req_resp import BaseRequest, BaseResponse


class AnalysisResponse(BaseResponse[models_ai.AnalysisResult]):
    """Response envelope containing a text-based AI analysis."""


# ----------------------------------------------------------------------#


class AnalyzeTickerRequest(BaseRequest):
    """Request a ticker analysis for a specified investment intent."""

    symbol: str = Field(
        default="",
        description="Security symbol in Yahoo Finance or EXCHANGE:CODE format.",
    )
    intent: str = Field(
        default=service_analyze_ticker.DEFAULT_INTENT,
        description="Analysis objective or perspective applied to the security.",
    )


class AIVendorsResponse(BaseResponse[dict[str, models_ai.AIVendorInfo]]):
    """Response envelope containing enabled AI vendors, tiers, and models."""

    data: dict[str, models_ai.AIVendorInfo] = Field(
        default={},
        description="Enabled AI vendors keyed by vendor identifier.",
    )


# ----------------------------------------------------------------------#


class AnalyzeTickerAsyncResponse(async_task.AsyncTaskResponse[models_ai.AnalysisResult]):
    """Background-task response for ticker analysis."""
