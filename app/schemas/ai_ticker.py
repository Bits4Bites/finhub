from __future__ import annotations

from typing import Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from ..models import ai_ticker as models_ticker
from . import async_task
from .base_req_resp import BaseRequest, BaseResponse


class TickerHoldingInput(BaseRequest):
    """Optional current holding context for a ticker recommendation."""

    model_config = ConfigDict(extra="forbid")

    num_shares: float = Field(
        gt=0,
        allow_inf_nan=False,
        description="Positive number of shares or units currently held.",
    )
    avg_price: float = Field(
        gt=0,
        allow_inf_nan=False,
        description="Positive average acquisition price in the security's trading currency.",
    )


class AnalyzeTickerRequest(BaseRequest):
    """Request structured research, forecasts, and a generic ticker recommendation."""

    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(
        min_length=1,
        max_length=32,
        description="Security symbol in Yahoo Finance or EXCHANGE:CODE format.",
    )
    intent: str | None = Field(
        default=None,
        min_length=1,
        max_length=4000,
        description="Optional analysis focus that cannot override required output behavior.",
    )
    current_holding: TickerHoldingInput | None = Field(
        default=None,
        description="Optional current holding used only for recommendation context.",
    )

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("intent", mode="before")
    @classmethod
    def normalize_intent(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_symbol(self) -> Self:
        if any(character.isspace() for character in self.symbol):
            raise ValueError("symbol cannot contain whitespace")
        return self


class AnalyzeTickerResponse(BaseResponse[models_ticker.TickerAnalysis]):
    """Response envelope containing structured ticker analysis."""


class AnalyzeTickerAsyncResponse(async_task.AsyncTaskResponse[models_ticker.TickerAnalysis]):
    """Background-task response for structured ticker analysis."""
