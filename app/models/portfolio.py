from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_COMPANY_NAME_LENGTH = 200
MAX_EXCHANGE_LENGTH = 32
MAX_TAGS_LENGTH = 500
MAX_TICKER_LENGTH = 32

PortfolioPriceSource = Literal["MarketData", "Client"]


class PortfolioHolding(BaseModel):
    """A caller-supplied position shared by portfolio features."""

    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(
        min_length=1,
        max_length=MAX_TICKER_LENGTH,
        description="Security symbol in Yahoo Finance or EXCHANGE:CODE format.",
    )
    num_shares: float = Field(
        default=0.0,
        ge=0,
        allow_inf_nan=False,
        description="Non-negative number of shares or units held.",
    )
    avg_price: float = Field(
        default=0.0,
        ge=0,
        allow_inf_nan=False,
        description="Non-negative average acquisition price per share or unit.",
    )
    market_price: float | None = Field(
        default=None,
        gt=0,
        allow_inf_nan=False,
        description="Optional positive client-supplied market price per share or unit.",
    )
    target_allocation: float | None = Field(
        default=None,
        ge=0,
        le=1,
        allow_inf_nan=False,
        description="Optional target portfolio weight expressed from zero through one.",
    )
    tags: str | None = Field(
        default=None,
        max_length=MAX_TAGS_LENGTH,
        description="Optional user-supplied metadata associated with the holding.",
    )

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
    """A portfolio position enriched and validated against market data."""

    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(
        min_length=1,
        max_length=MAX_TICKER_LENGTH,
        description="Canonical security symbol used by the verified portfolio.",
    )
    company_name: str | None = Field(
        max_length=MAX_COMPANY_NAME_LENGTH,
        description="Issuer or security name, or null when market data does not provide one.",
    )
    exchange: str = Field(
        min_length=1,
        max_length=MAX_EXCHANGE_LENGTH,
        description="Normalized exchange code for the security.",
    )
    currency: str = Field(
        min_length=3,
        max_length=3,
        description="Three-letter trading currency code.",
    )
    num_shares: float = Field(
        gt=0,
        allow_inf_nan=False,
        description="Positive number of shares or units included in the analysis.",
    )
    avg_price: float = Field(
        ge=0,
        allow_inf_nan=False,
        description="Average acquisition price per share or unit.",
    )
    market_price: float = Field(
        gt=0,
        allow_inf_nan=False,
        description="Verified market price used to value the holding.",
    )
    price_source: PortfolioPriceSource = Field(description="Origin of the market price used for valuation.")
    market_value: float = Field(
        gt=0,
        allow_inf_nan=False,
        description="Current market value of the holding.",
    )
    current_allocation: float = Field(
        gt=0,
        le=1,
        allow_inf_nan=False,
        description="Current portfolio weight expressed from zero through one.",
    )
    target_allocation: float | None = Field(
        ge=0,
        le=1,
        allow_inf_nan=False,
        description="Requested target portfolio weight, or null when not supplied.",
    )
    allocation_drift: float | None = Field(
        ge=-1,
        le=1,
        allow_inf_nan=False,
        description="Current allocation minus target allocation, or null without a target.",
    )
    unrealized_profit_loss: float | None = Field(
        allow_inf_nan=False,
        description="Unrealized profit or loss based on average price, or null when unavailable.",
    )
    tags: str | None = Field(
        max_length=MAX_TAGS_LENGTH,
        description="Optional user-supplied metadata associated with the holding.",
    )

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
