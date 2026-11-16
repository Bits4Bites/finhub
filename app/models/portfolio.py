from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..utils import conv
from . import types as models_types

MAX_COMPANY_NAME_LENGTH = 200
MAX_EXCHANGE_LENGTH = 32
MAX_TAGS_LENGTH = 500
MAX_TICKER_LENGTH = 32

PortfolioPriceSource = Literal["MarketData", "Client"]
PortfolioBudgetType = Literal["NotProvided", "Total", "Recurring"]
PortfolioBudgetFrequency = Literal["Weekly", "Fortnightly", "Monthly", "Quarterly", "Annually"]


def normalize_canonical_ticker(value: object) -> object:
    """Normalize an exchange-qualified ticker for portfolio contracts.

    Args:
        value: A candidate ticker. String values must use ``EXCHANGE:CODE``
            format; surrounding whitespace is trimmed, letters are uppercased,
            and recognized exchange aliases are replaced with their canonical
            exchange code. Non-string values are returned unchanged so a
            Pydantic before-validator can report the target field's type error.

    Returns:
        The normalized ``EXCHANGE:CODE`` string, preserving an unknown exchange
        after trimming and uppercasing, or the original non-string value.

    Raises:
        ValueError: If a string has an empty exchange or code, embedded
            whitespace, or anything other than one separating colon.
    """
    if not isinstance(value, str):
        return value
    normalized = value.strip().upper()
    parts = normalized.split(":")
    if len(parts) != 2 or not all(parts) or any(character.isspace() for character in normalized):
        raise ValueError("ticker must use canonical EXCHANGE:CODE format")
    exchange, ticker = parts
    return f"{conv.normalize_exchange_code(exchange)}:{ticker}"


class PortfolioBudget(BaseModel):
    """Supplied or application-inferred new money available for portfolio actions.

    ``NotProvided`` carries no budget details. ``Total`` requires a supplied
    amount, currency, and source text without a frequency. ``Recurring``
    requires those details plus a frequency when investor supplied, while an
    inferred recurring budget must not invent a frequency.
    """

    model_config = ConfigDict(extra="forbid")

    budget_type: PortfolioBudgetType = Field(
        description="Whether no budget is available, or new money is a total amount or recurring contribution."
    )
    is_inferred: bool = Field(
        description="Whether the application inferred the recurring next-iteration budget from current holdings."
    )
    amount: float | None = Field(
        gt=0,
        allow_inf_nan=False,
        description="Positive new-money amount for one action-plan iteration, or null when no budget is available.",
    )
    currency: models_types.CurrencyCode | None = Field(
        description=(
            "Three-letter budget currency, or null when no budget is available; string input is trimmed and uppercased."
        ),
    )
    frequency: PortfolioBudgetFrequency | None = Field(
        description="Investor-supplied contribution frequency, or null for total and inferred next-iteration budgets.",
    )
    source_text: str | None = Field(
        min_length=1,
        max_length=500,
        description="Exact investor-theme excerpt or deterministic explanation of an inferred budget.",
    )

    @model_validator(mode="after")
    def validate_budget(self) -> Self:
        if self.budget_type == "NotProvided":
            if self.is_inferred or any(
                value is not None for value in (self.amount, self.currency, self.frequency, self.source_text)
            ):
                raise ValueError("NotProvided budget cannot contain budget details")
        elif self.budget_type == "Total":
            if self.amount is None or self.currency is None or self.source_text is None:
                raise ValueError("Total budget requires amount, currency, and source_text")
            if self.is_inferred:
                raise ValueError("Total budget cannot be application-inferred")
            if self.frequency is not None:
                raise ValueError("Total budget cannot contain a recurring frequency")
        elif self.amount is None or self.currency is None or self.source_text is None:
            raise ValueError("Recurring budget requires amount, currency, and source_text")
        elif self.is_inferred and self.frequency is not None:
            raise ValueError("Inferred recurring budget cannot invent a contribution frequency")
        elif not self.is_inferred and self.frequency is None:
            raise ValueError("Investor-supplied recurring budget requires a frequency")
        return self


class PortfolioHolding(BaseModel):
    """A caller-supplied position shared by portfolio features."""

    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(
        min_length=1,
        max_length=MAX_TICKER_LENGTH,
        description=(
            "Security symbol in Yahoo Finance or EXCHANGE:CODE format; surrounding "
            "whitespace is trimmed, letters are uppercased, and exchange aliases are canonicalized."
        ),
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
        if not isinstance(value, str):
            return value
        normalized = value.strip().upper()
        if any(character.isspace() for character in normalized):
            raise ValueError("ticker cannot contain whitespace")
        return normalize_canonical_ticker(normalized) if ":" in normalized else normalized

    @field_validator("tags", mode="before")
    @classmethod
    def normalize_tags(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        return normalized or None


class PortfolioVerifiedHolding(BaseModel):
    """A portfolio position whose service-verified values are supplied by the caller.

    The model validates field contracts but does not recompute valuation,
    allocation, drift, or profit-and-loss fields. Its normalized exchange must
    match the canonical ticker prefix.
    """

    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(
        min_length=1,
        max_length=MAX_TICKER_LENGTH,
        description=(
            "Canonical EXCHANGE:CODE security symbol used by the verified portfolio; "
            "input is trimmed, uppercased, and exchange aliases are canonicalized."
        ),
    )
    company_name: str | None = Field(
        max_length=MAX_COMPANY_NAME_LENGTH,
        description="Issuer or security name, or null when market data does not provide one.",
    )
    exchange: str = Field(
        min_length=1,
        max_length=MAX_EXCHANGE_LENGTH,
        description=(
            "Normalized exchange code for the security; input is trimmed, "
            "uppercased, and recognized aliases are canonicalized."
        ),
    )
    currency: models_types.CurrencyCode = Field(
        description="Three-letter trading currency code; input is trimmed and uppercased.",
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
        description="Service-verified current market value supplied for the holding.",
    )
    current_allocation: float = Field(
        gt=0,
        le=1,
        allow_inf_nan=False,
        description="Service-verified current portfolio weight supplied from greater than zero through one.",
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
        description="Service-verified supplied allocation drift, or null without a target.",
    )
    unrealized_profit_loss: float | None = Field(
        allow_inf_nan=False,
        description="Service-verified supplied unrealized profit or loss, or null when unavailable.",
    )
    tags: str | None = Field(
        max_length=MAX_TAGS_LENGTH,
        description="Optional user-supplied metadata associated with the holding.",
    )

    @field_validator("ticker", mode="before")
    @classmethod
    def normalize_ticker(cls, value: object) -> object:
        return normalize_canonical_ticker(value)

    @field_validator("exchange", mode="before")
    @classmethod
    def normalize_exchange(cls, value: object) -> object:
        return conv.normalize_exchange_code(value) if isinstance(value, str) else value

    @field_validator("company_name", "tags", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_identity(self) -> Self:
        ticker_exchange, _ = self.ticker.split(":", 1)
        if self.exchange != ticker_exchange:
            raise ValueError("holding exchange must match the canonical ticker")
        return self
