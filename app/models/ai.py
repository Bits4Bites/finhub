from datetime import UTC, date, datetime, time
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator

ReferenceSourceType = Literal["Regulatory", "Exchange", "Issuer", "MarketData", "Research", "News", "Other"]


class ReferenceSource(BaseModel):
    """
    A verifiable source referenced by an AI-generated response.

    Attributes:
        id: Stable source identifier, unique within the containing API response.
        title: Human-readable title of the source or document.
        publisher: Publisher or organization responsible for the source.
        source_type: Generic category used to evaluate and group the source.
        published_at: Publication date or datetime normalized to UTC, or None when unavailable.
        accessed_at: Retrieval date or datetime normalized to UTC.
        url: Canonical HTTPS URL for the source.
    """

    id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
    title: str = Field(min_length=1, max_length=500)
    publisher: str = Field(min_length=1, max_length=200)
    source_type: ReferenceSourceType
    published_at: datetime | None
    accessed_at: datetime
    url: HttpUrl

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


class AIVendorInfo(BaseModel):
    name: str = ""
    tier_models: dict[str, list[str]] = {}  # map {tier -> list of models}


class BaseAIResult(BaseModel):
    llm_error: bool = False
    llm_error_msg: str | None = None
    llm_response: str | None = None


class AnalysisResult(BaseAIResult):
    analysis: str = ""


class AnalyzePortfolioResult(BaseAIResult):
    analysis: str = ""
    rebalance_plan: str = ""
