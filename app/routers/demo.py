from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from ..models import demo as models
from ..schemas import demo as schemas
from ..utils import demo as utils

router = APIRouter(prefix="/demo", tags=["demo"])


@router.get("/", response_model=schemas.DemoHelloResponse, response_model_exclude_none=True)
def demo_hello():
    return schemas.DemoHelloResponse()


ItemStore: dict[str, models.DemoItem] = {}


@router.post(
    "/items",
    status_code=status.HTTP_201_CREATED,
    response_model=schemas.DemoItemResponse,
    response_model_exclude_none=True,
)
def demo_create_item(item_request: schemas.DemoCreateOrUpdateItemRequest):
    # Simulate item creation (in a real app, you'd save to a database)
    new_item = models.DemoItem(
        id=utils.generate_demo_item_id(),
        name=item_request.name,
        description=item_request.description,
        price=item_request.price,
    )
    ItemStore[new_item.id] = new_item
    return schemas.DemoItemResponse(status=201, message="Item created successfully.", data=new_item)


@router.get("/items/{item_id}", response_model=schemas.DemoItemResponse, response_model_exclude_none=True)
def demo_get_item(item_id: str):
    item = ItemStore.get(item_id)
    if not item:
        return JSONResponse(
            content=schemas.DemoItemResponse(status=404, message="Item not found", data=None).model_dump(),
            status_code=404,
        )
    return schemas.DemoItemResponse(data=item, message="ok")


@router.put("/items/{item_id}", response_model=schemas.DemoItemResponse, response_model_exclude_none=True)
def demo_update_item(item_id: str, item_request: schemas.DemoCreateOrUpdateItemRequest):
    item = ItemStore.get(item_id)
    if not item:
        return JSONResponse(
            content=schemas.DemoItemResponse(status=404, message="Item not found", data=None).model_dump(),
            status_code=404,
        )
    # Update item details
    item.name = item_request.name
    item.description = item_request.description
    item.price = item_request.price
    ItemStore[item_id] = item
    return schemas.DemoItemResponse(data=item, message="Item updated successfully.")


@router.delete("/items/{item_id}", response_model=schemas.DemoBaseResponse, response_model_exclude_none=True)
def demo_delete_item(item_id: str):
    if item_id in ItemStore:
        del ItemStore[item_id]
    return schemas.DemoBaseResponse(status=200, message="Item deleted successfully.")  # always return success
