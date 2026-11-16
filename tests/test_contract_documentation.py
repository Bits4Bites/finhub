import importlib
import inspect
import pkgutil
import types

import pytest
from pydantic import BaseModel

from app import models, schemas
from app.models import events_listings as models_events_listings
from app.models import market as models_market
from app.models import market_data as models_market_data
from app.models import stocks as models_stocks

CALLER_INVOKED_MODEL_METHODS = (
    models_events_listings.ListingAnalysisBase.referenced_source_ids,
    models_market.CompanyBriefInfo.extract_exchange_code,
    models_market_data.HistoryPoint.to_currency,
    models_market_data.StockQuote.__init__,
    models_market_data.StockQuote.to_currency,
    models_stocks.SymbolBase.__init__,
    models_stocks.SymbolOverview.__init__,
    models_stocks.SymbolDividend.__init__,
    models_stocks.StockHistory.__init__,
    models_stocks.SymbolInfo.__init__,
)


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
    "method",
    CALLER_INVOKED_MODEL_METHODS,
    ids=lambda method: f"{method.__module__}.{method.__qualname__}",
)
def test_caller_invoked_model_methods_have_documentation(method):
    assert inspect.getdoc(method), f"{method.__module__}.{method.__qualname__} has no documentation"
