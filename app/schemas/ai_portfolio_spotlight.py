from typing import Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from ..models import ai_portfolio_spotlight as models_spotlight
from ..models import portfolio as models_portfolio
from . import async_task
from .base_req_resp import BaseRequest, BaseResponse


class PortfolioSpotlightRequest(BaseRequest):
    """Request a quick, structured review of current portfolio risks and actions."""

    model_config = ConfigDict(extra="forbid")

    country: str = Field(
        min_length=2,
        max_length=64,
        description="Portfolio market country as an ISO code or country name.",
    )
    current_allocation: list[models_portfolio.PortfolioHolding] = Field(
        min_length=1,
        max_length=50,
        description="Current positions. At least one position must have a positive share count.",
    )
    investor_theme: str = Field(
        min_length=1,
        max_length=4000,
        description="Required investor risk tolerance, horizon, goals, and relevant portfolio preferences.",
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
        if not any(holding.num_shares > 0 for holding in self.current_allocation):
            raise ValueError("current_allocation must contain at least one positive-share position")
        return self


class PortfolioSpotlightResponse(BaseResponse[models_spotlight.PortfolioSpotlightAnalysis]):
    """Response envelope containing a structured portfolio spotlight review."""


class PortfolioSpotlightAsyncResponse(async_task.AsyncTaskResponse[models_spotlight.PortfolioSpotlightAnalysis]):
    """Background-task response for portfolio spotlight analysis."""
