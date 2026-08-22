from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_COMPANY_NAME_LENGTH = 200
MAX_EXCHANGE_LENGTH = 32
MAX_TAGS_LENGTH = 500
MAX_TICKER_LENGTH = 32

PortfolioPriceSource = Literal["MarketData", "Client"]


class PortfolioHolding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(min_length=1, max_length=MAX_TICKER_LENGTH)
    num_shares: float = Field(default=0.0, ge=0, allow_inf_nan=False)
    avg_price: float = Field(default=0.0, ge=0, allow_inf_nan=False)
    market_price: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    target_allocation: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    tags: str | None = Field(default=None, max_length=MAX_TAGS_LENGTH)

    @field_validator("ticker", mode="before")
    @classmethod
    def normalize_ticker(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("tags", mode="before")
    @classmethod
    def normalize_tags(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        return normalized or None


class PortfolioVerifiedHolding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(min_length=1, max_length=MAX_TICKER_LENGTH)
    company_name: str | None = Field(max_length=MAX_COMPANY_NAME_LENGTH)
    exchange: str = Field(min_length=1, max_length=MAX_EXCHANGE_LENGTH)
    currency: str = Field(min_length=3, max_length=3)
    num_shares: float = Field(gt=0, allow_inf_nan=False)
    avg_price: float = Field(ge=0, allow_inf_nan=False)
    market_price: float = Field(gt=0, allow_inf_nan=False)
    price_source: PortfolioPriceSource
    market_value: float = Field(gt=0, allow_inf_nan=False)
    current_allocation: float = Field(gt=0, le=1, allow_inf_nan=False)
    target_allocation: float | None = Field(ge=0, le=1, allow_inf_nan=False)
    allocation_drift: float | None = Field(ge=-1, le=1, allow_inf_nan=False)
    unrealized_profit_loss: float | None = Field(allow_inf_nan=False)
    tags: str | None = Field(max_length=MAX_TAGS_LENGTH)

    @field_validator("ticker", "exchange", "currency", mode="before")
    @classmethod
    def normalize_code(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("company_name", "tags", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        return normalized or None
