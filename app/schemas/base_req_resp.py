from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

ResponseDataT = TypeVar("ResponseDataT")


class BaseRequest(BaseModel):
    """Base request contract for API payloads."""

    model_config = {"arbitrary_types_allowed": True}


class BaseResponse(BaseModel, Generic[ResponseDataT]):  # noqa: UP046
    """Generic API response envelope shared by synchronous endpoints."""

    status: int = Field(description="Application status code for the response.")
    message: str = Field(description="Human-readable response summary.")
    data: ResponseDataT | None = Field(
        default=None,
        description="Endpoint result payload, or null when no result is available.",
    )
    extra: Any | None = Field(
        default=None,
        description="Optional endpoint-specific response metadata.",
    )
    model_config = {"arbitrary_types_allowed": True}
