from pydantic import BaseModel
from typing import Optional, Any

from ..models import demo as models


class DemoBaseResponse(BaseModel):
    status: int
    message: str
    data: Optional[Any] = None

    model_config = {"arbitrary_types_allowed": True}


class DemoHelloResponse(DemoBaseResponse):
    status: int = 200
    message: str = "Hello, World!"


class DemoCreateOrUpdateItemRequest(BaseModel):
    name: str
    description: Optional[str] = None
    price: float


class DemoItemResponse(DemoBaseResponse):
    status: int = 200
    message: str = "Ok"
    data: Optional[models.DemoItem] = None
