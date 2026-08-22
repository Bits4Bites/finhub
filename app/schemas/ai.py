from pydantic import Field

from ..models import ai as models_ai
from ..models import portfolio as models_portfolio
from ..services import ai as services_ai
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


# ----------------------------------------------------------------------#


class AnalyzePortfolioRequest(BaseRequest):
    """Request portfolio construction or review using an investor profile."""

    country: str = Field(description="Country context used for market and portfolio analysis.")
    current_allocation: list[models_portfolio.PortfolioHolding] = Field(
        default=[],
        description="Current holdings; an empty list requests construction of a new portfolio.",
    )
    investor_theme: str = Field(
        default=services_ai.DEFAULT_INVESTOR_THEME,
        description="Investor risk tolerance, horizon, goals, and portfolio preferences.",
    )
    rebalance_plan: bool = Field(
        default=False,
        description="Whether a review may produce a major-rebalance plan when one is needed.",
    )


class AnalyzePortfolioResponse(AnalysisResponse):
    """Response envelope containing a portfolio-construction analysis."""

    pass


class ReviewPortfolioResponse(BaseResponse[models_ai.AnalyzePortfolioResult]):
    """Response envelope containing a portfolio review and optional rebalance plan."""


# ----------------------------------------------------------------------#


class AIVendorsResponse(BaseResponse[dict[str, models_ai.AIVendorInfo]]):
    """Response envelope containing enabled AI vendors, tiers, and models."""

    data: dict[str, models_ai.AIVendorInfo] = Field(
        default={},
        description="Enabled AI vendors keyed by vendor identifier.",
    )


# ----------------------------------------------------------------------#


class AnalyzeTickerAsyncResponse(async_task.AsyncTaskResponse[models_ai.AnalysisResult]):
    """Background-task response for ticker analysis."""


class BuildPortfolioAsyncResponse(async_task.AsyncTaskResponse[models_ai.AnalyzePortfolioResult]):
    """Background-task response for portfolio construction."""


class AnalyzePortfolioAsyncResponse(async_task.AsyncTaskResponse[models_ai.AnalyzePortfolioResult]):
    """Background-task response for portfolio review or construction."""
