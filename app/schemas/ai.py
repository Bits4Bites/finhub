from pydantic import Field, field_validator

from ..models import ai as models_ai
from ..models import ai_portfolio_construction as models_construction
from ..models import portfolio as models_portfolio
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
    investor_theme: str | None = Field(
        default=None,
        min_length=1,
        max_length=4000,
        description="Investor context; required for construction and optional for existing-portfolio review.",
    )
    rebalance_plan: bool = Field(
        default=False,
        description="Whether a review may produce a major-rebalance plan when one is needed.",
    )

    @field_validator("investor_theme", mode="before")
    @classmethod
    def normalize_investor_theme(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        return normalized or None


class AnalyzePortfolioResponse(
    BaseResponse[models_ai.AnalyzePortfolioResult | models_construction.PortfolioConstruction]
):
    """Response envelope containing a portfolio review or constructed target portfolio."""


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


class AnalyzePortfolioAsyncResponse(
    async_task.AsyncTaskResponse[models_ai.AnalyzePortfolioResult | models_construction.PortfolioConstruction]
):
    """Background-task response for portfolio review or construction."""
