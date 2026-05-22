from typing import Any

from pydantic import BaseModel


class BaseRequest(BaseModel):
    model_config = {"arbitrary_types_allowed": True}


class BaseResponse(BaseModel):
    status: int
    message: str
    data: Any | None = None
    extra: Any | None = None
    model_config = {"arbitrary_types_allowed": True}
