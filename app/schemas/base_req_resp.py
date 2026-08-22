from typing import Any, Generic, TypeVar

from pydantic import BaseModel

ResponseDataT = TypeVar("ResponseDataT")


class BaseRequest(BaseModel):
    model_config = {"arbitrary_types_allowed": True}


class BaseResponse(BaseModel, Generic[ResponseDataT]):  # noqa: UP046
    status: int
    message: str
    data: ResponseDataT | None = None
    extra: Any | None = None
    model_config = {"arbitrary_types_allowed": True}
