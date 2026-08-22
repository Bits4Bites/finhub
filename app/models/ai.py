from datetime import UTC, date, datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

ReferenceSourceType = Literal["Regulatory", "Exchange", "Issuer", "MarketData", "Research", "News", "Other"]


class StrictAIModel(BaseModel):
    """Base model for AI contracts that reject undeclared fields."""

    model_config = ConfigDict(extra="forbid")


class ReferenceSourceMetadata(StrictAIModel):
    """Structured metadata describing a source cited by an AI response."""

    id: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
        description="Source identifier unique within the containing response.",
    )
    title: str = Field(
        min_length=1,
        max_length=500,
        description="Human-readable title of the cited source or document.",
    )
    publisher: str = Field(
        min_length=1,
        max_length=200,
        description="Publisher or organization responsible for the source.",
    )
    source_type: ReferenceSourceType = Field(description="Category used to classify and evaluate the source.")
    published_at: datetime | None = Field(description="UTC publication timestamp, or null when unavailable.")
    accessed_at: datetime = Field(description="UTC timestamp when the source was retrieved.")
    url: HttpUrl = Field(description="Canonical HTTPS URL of the source.")

    @field_validator("id", "title", "publisher", mode="before")
    @classmethod
    def strip_required_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("published_at", "accessed_at", mode="before")
    @classmethod
    def expand_date_only(cls, value: object) -> object:
        if value is None or isinstance(value, datetime):
            return value
        if isinstance(value, date):
            return datetime.combine(value, time.min)
        if isinstance(value, str):
            try:
                return datetime.combine(date.fromisoformat(value), time.min)
            except ValueError:
                return value
        return value

    @field_validator("published_at", "accessed_at")
    @classmethod
    def normalize_to_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @field_validator("url")
    @classmethod
    def require_https(cls, value: HttpUrl) -> HttpUrl:
        if value.scheme != "https":
            raise ValueError("url must use HTTPS")
        return value


class ReferenceSource(ReferenceSourceMetadata):
    """
    A source referenced by a returned AI-generated response.

    Attributes:
        id: Stable source identifier, unique within the containing API response.
        title: Human-readable title of the source or document.
        publisher: Publisher or organization responsible for the source.
        source_type: Generic category used to evaluate and group the source.
        published_at: Publication date or datetime normalized to UTC, or None when unavailable.
        accessed_at: Retrieval date or datetime normalized to UTC.
        url: Canonical HTTPS URL for the source.
        is_verified: Whether the application verified the source attribution.
    """

    is_verified: bool = Field(description="Whether provider citations verified that the response used this source.")


class AIVendorInfo(BaseModel):
    """Enabled model tiers exposed for an AI vendor."""

    name: str = Field(default="", description="Display name of the AI vendor.")
    tier_models: dict[str, list[str]] = Field(
        default={},
        description="Enabled model identifiers grouped by service tier.",
    )


class BaseAIResult(BaseModel):
    """Common execution metadata returned by legacy AI workflows."""

    llm_error: bool = Field(
        default=False,
        description="Whether the language-model execution failed.",
    )
    llm_error_msg: str | None = Field(
        default=None,
        description="Language-model failure detail, or null when execution succeeded.",
    )
    llm_response: str | None = Field(
        default=None,
        description="Raw language-model response retained by the workflow, when available.",
    )


class AnalysisResult(BaseAIResult):
    """Text analysis returned by a legacy AI endpoint."""

    analysis: str = Field(default="", description="Generated analysis content.")


class AnalyzePortfolioResult(BaseAIResult):
    """Legacy portfolio analysis and optional rebalance-plan result."""

    analysis: str = Field(default="", description="Generated portfolio analysis content.")
    rebalance_plan: str = Field(
        default="",
        description="Generated rebalance plan, or an empty string when no plan was requested.",
    )
