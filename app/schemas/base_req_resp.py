from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

ResponseDataT = TypeVar("ResponseDataT")


class BaseRequest(BaseModel):
    """Base request contract for API payloads."""

    model_config = {"arbitrary_types_allowed": True}


class BaseResponse(BaseModel, Generic[ResponseDataT]):  # noqa: UP046
    """Generic API response envelope shared by synchronous endpoints.

    Endpoints configured to exclude null values omit unavailable ``data`` and
    ``extra`` fields from the serialized response.
    """

    status: int = Field(description="Application status code for the response.")
    message: str = Field(description="Human-readable response summary.")
    data: ResponseDataT | None = Field(
        default=None,
        description="Endpoint result payload, omitted by null-excluding endpoints when unavailable.",
    )
    extra: Any | None = Field(
        default=None,
        description="Optional endpoint-specific metadata, omitted by null-excluding endpoints when unavailable.",
    )
    model_config = {"arbitrary_types_allowed": True}
