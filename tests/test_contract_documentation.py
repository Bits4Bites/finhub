import importlib
import inspect
import pkgutil
import types

import pytest
from pydantic import BaseModel

from app import models, routers, schemas
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


def _model_functions() -> list[types.FunctionType]:
    result: list[types.FunctionType] = []
    for module_info in pkgutil.iter_modules(models.__path__, f"{models.__name__}."):
        module = importlib.import_module(module_info.name)
        result.extend(
            function
            for name, function in inspect.getmembers(module, inspect.isfunction)
            if not name.startswith("_") and function.__module__ == module.__name__
        )
    return result


def _router_functions() -> list[types.FunctionType]:
    result: list[types.FunctionType] = []
    for module_info in pkgutil.iter_modules(routers.__path__, f"{routers.__name__}."):
        module = importlib.import_module(module_info.name)
        result.extend(
            function
            for name, function in inspect.getmembers(module, inspect.isfunction)
            if not name.startswith("_") and function.__module__ == module.__name__
        )
    return result


@pytest.mark.parametrize("model_type", _contract_models(), ids=lambda model_type: model_type.__name__)
def test_contract_models_document_classes_and_fields(model_type):
    assert inspect.getdoc(model_type)
    assert all(field_info.description for field_info in model_type.model_fields.values()), (
        f"{model_type.__name__} has undocumented fields"
    )


@pytest.mark.parametrize(
    "function",
    _model_functions(),
    ids=lambda function: f"{function.__module__}.{function.__name__}",
)
def test_model_module_functions_have_documentation(function):
    assert inspect.getdoc(function), f"{function.__module__}.{function.__name__} has no documentation"


@pytest.mark.parametrize(
    "function",
    _router_functions(),
    ids=lambda function: f"{function.__module__}.{function.__name__}",
)
def test_router_module_functions_have_documentation(function):
    assert inspect.getdoc(function), f"{function.__module__}.{function.__name__} has no documentation"


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
