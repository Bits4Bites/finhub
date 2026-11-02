from typing import Annotated, Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from ..models import ai_portfolio_construction as models_construction
from ..models import ai_portfolio_review as models_review
from ..models import portfolio as models_portfolio
from . import async_task
from .base_req_resp import BaseRequest, BaseResponse

AnalyzePortfolioResult = Annotated[
    models_construction.PortfolioConstruction | models_review.PortfolioReview,
    Field(discriminator="result_type"),
]


class AnalyzePortfolioRequest(BaseRequest):
    """Request deterministic dispatch to portfolio construction or structured review."""

    model_config = ConfigDict(extra="forbid")

    country: str = Field(
        min_length=2,
        max_length=64,
        description="Target market country as an ISO code or country name.",
    )
    current_allocation: list[models_portfolio.PortfolioHolding] = Field(
        default_factory=list,
        max_length=50,
        description="Submitted whole-share positions, including optional zero-share positions used for routing.",
    )
    investor_theme: str = Field(
        min_length=1,
        max_length=4000,
        description=(
            "Required investor goals, strategy, constraints, risk context, and optional total or recurring budget."
        ),
    )
    rebalance_plan: bool = Field(
        default=False,
        description="Whether to include execution actions when a major rebalance is recommended.",
    )

    @field_validator("country", "investor_theme", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_holdings(self) -> Self:
        tickers = [holding.ticker for holding in self.current_allocation]
        if len(tickers) != len(set(tickers)):
            raise ValueError("current_allocation tickers must be unique")
        if any(
            holding.num_shares > 0 and not float(holding.num_shares).is_integer() for holding in self.current_allocation
        ):
            raise ValueError("current_allocation supports whole-share holdings only")
        return self


class AnalyzePortfolioResponse(BaseResponse[AnalyzePortfolioResult]):
    """Response envelope containing a structured review or constructed portfolio."""


class AnalyzePortfolioAsyncResponse(async_task.AsyncTaskResponse[AnalyzePortfolioResult]):
    """Background-task response for portfolio review or construction."""
