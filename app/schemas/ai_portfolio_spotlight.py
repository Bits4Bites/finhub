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
        default_factory=list,
        max_length=50,
        description="Current positions. An empty list or only zero-share positions returns a deterministic empty result.",
    )
    investor_theme: str | None = Field(
        default=None,
        min_length=1,
        max_length=4000,
        description="Optional investor risk tolerance, horizon, goals, and relevant portfolio preferences.",
    )

    @field_validator("country")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("investor_theme", mode="before")
    @classmethod
    def normalize_investor_theme(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_tickers(self) -> Self:
        tickers = [holding.ticker for holding in self.current_allocation]
        if len(tickers) != len(set(tickers)):
            raise ValueError("current_allocation tickers must be unique")
        return self


class PortfolioSpotlightResponse(BaseResponse[models_spotlight.PortfolioSpotlightAnalysis]):
    pass


class PortfolioSpotlightAsyncResponse(async_task.AsyncTaskResponse[models_spotlight.PortfolioSpotlightAnalysis]):
    pass
