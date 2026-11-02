import importlib
import inspect
import pkgutil

import pytest
from pydantic import BaseModel

from app import models, schemas
from app.main import app


def _contract_models() -> list[type[BaseModel]]:
    result: list[type[BaseModel]] = []
    for package in (models, schemas):
        for module_info in pkgutil.iter_modules(package.__path__, f"{package.__name__}."):
            module = importlib.import_module(module_info.name)
            result.extend(
                model_type
                for _, model_type in inspect.getmembers(module, inspect.isclass)
                if issubclass(model_type, BaseModel)
                and model_type is not BaseModel
                and model_type.__module__ == module.__name__
            )
    return result


@pytest.mark.parametrize("model_type", _contract_models(), ids=lambda model_type: model_type.__name__)
def test_contract_models_document_classes_and_fields(model_type):
    assert inspect.getdoc(model_type)
    assert all(field_info.description for field_info in model_type.model_fields.values()), (
        f"{model_type.__name__} has undocumented fields"
    )


def test_application_openapi_components_document_classes_and_fields():
    framework_components = {"HTTPValidationError", "ValidationError"}
    component_schemas = app.openapi()["components"]["schemas"]

    for name, schema in component_schemas.items():
        if name in framework_components:
            continue
        assert schema.get("description"), f"{name} has no class description"
        assert all(property_schema.get("description") for property_schema in schema.get("properties", {}).values()), (
            f"{name} has undocumented fields"
        )
