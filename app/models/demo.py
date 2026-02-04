from pydantic import BaseModel
from typing import Optional


class DemoItem(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    price: float
