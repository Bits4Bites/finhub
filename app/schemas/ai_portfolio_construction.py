from typing import Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from ..models import ai_portfolio_construction as models_construction
from ..models import portfolio as models_portfolio
from . import async_task
from .base_req_resp import BaseRequest, BaseResponse


class BuildPortfolioRequest(BaseRequest):
    """Request construction of one target portfolio from a required investor theme."""

    model_config = ConfigDict(extra="forbid")

    country: str = Field(
        min_length=2,
        max_length=64,
        description="Target market country as an ISO code or country name.",
    )
    investor_theme: str = Field(
        min_length=1,
        max_length=4000,
        description="Required investor goals, constraints, preferences, horizon, and risk context.",
    )
    current_allocation: list[models_portfolio.PortfolioHolding] = Field(
        default_factory=list,
        max_length=50,
        description="Optional starting positions; zero-share positions are ignored during construction.",
    )

    @field_validator("country", "investor_theme", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_tickers(self) -> Self:
        tickers = [holding.ticker for holding in self.current_allocation]
        if len(tickers) != len(set(tickers)):
            raise ValueError("current_allocation tickers must be unique")
        return self


class BuildPortfolioResponse(BaseResponse[models_construction.PortfolioConstruction]):
    """Response envelope containing a structured target portfolio."""


class BuildPortfolioAsyncResponse(async_task.AsyncTaskResponse[models_construction.PortfolioConstruction]):
    """Background-task response for portfolio construction."""
