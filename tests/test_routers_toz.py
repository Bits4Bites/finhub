import types

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import market_data as models_market_data
from app.routers import toz

client = TestClient(app)


def _quote(currency: str, price: float) -> models_market_data.StockQuote:
    ticker = types.SimpleNamespace(
        info={
            "currency": currency,
            "regularMarketPrice": price,
        }
    )
    return models_market_data.StockQuote(ticker)


def _history(currency: str, days: int) -> list[models_market_data.HistoryPoint]:
    return [
        models_market_data.HistoryPoint(
            timestamp=1_735_689_600,
            timestamp_str="2025-01-01 00:00:00",
            currency=currency,
            open=float(days),
            high=float(days),
            low=float(days),
            close=float(days),
            volume=1,
        )
    ]


@pytest.mark.parametrize(
    ("path", "service_name", "base_price"),
    [
        ("/toz/gold/quote", "get_gold_quote", 2_650.0),
        ("/toz/silver/quote", "get_silver_quote", 31.5),
    ],
)
@pytest.mark.parametrize(
    ("currency_input", "expected_currency"),
    [(None, "USD"), ("aud", "AUD"), (" eur ", "EUR"), ("   ", "USD")],
)
def test_quote_endpoints_normalize_documented_currency_inputs(
    monkeypatch,
    path,
    service_name,
    base_price,
    currency_input,
    expected_currency,
):
    def fake_quote(currency):
        return _quote(currency, base_price + len(currency))

    monkeypatch.setattr(toz.toz_service, service_name, fake_quote)
    params = {} if currency_input is None else {"currency": currency_input}

    response = client.get(path, params=params)

    assert response.status_code == 200
    assert response.json()["status"] == 200
    assert response.json()["data"]["currency"] == expected_currency
    assert response.json()["data"]["market_price"] == base_price + len(expected_currency)


@pytest.mark.parametrize(
    ("path", "service_name"),
    [
        ("/toz/gold/quote", "get_gold_quote"),
        ("/toz/silver/quote", "get_silver_quote"),
    ],
)
def test_quote_endpoints_omit_unavailable_data(monkeypatch, path, service_name):
    monkeypatch.setattr(toz.toz_service, service_name, lambda currency: None)

    response = client.get(path, params={"currency": "XYZ"})

    assert response.status_code == 200
    assert response.json()["status"] == 200
    assert "data" not in response.json()


@pytest.mark.parametrize(
    ("path", "service_name"),
    [
        ("/toz/gold/history", "get_gold_history"),
        ("/toz/silver/history", "get_silver_history"),
    ],
)
@pytest.mark.parametrize(
    ("currency_input", "days_input", "expected_currency", "expected_days"),
    [
        (None, None, "USD", 30),
        ("eur", 7, "EUR", 7),
        (" aud ", 90, "AUD", 90),
        ("   ", 0, "USD", 30),
        ("USD", -5, "USD", 30),
    ],
)
def test_history_endpoints_expose_currency_and_day_normalization(
    monkeypatch,
    path,
    service_name,
    currency_input,
    days_input,
    expected_currency,
    expected_days,
):
    monkeypatch.setattr(toz.toz_service, service_name, _history)
    params = {}
    if currency_input is not None:
        params["currency"] = currency_input
    if days_input is not None:
        params["days"] = days_input

    response = client.get(path, params=params)

    assert response.status_code == 200
    assert response.json()["data"][0]["currency"] == expected_currency
    assert response.json()["data"][0]["close"] == expected_days


@pytest.mark.parametrize(
    ("path", "service_name", "provider_value", "has_data"),
    [
        ("/toz/gold/history", "get_gold_history", [], True),
        ("/toz/silver/history", "get_silver_history", [], True),
        ("/toz/gold/history", "get_gold_history", None, False),
        ("/toz/silver/history", "get_silver_history", None, False),
    ],
)
def test_history_endpoints_preserve_empty_and_unavailable_results(
    monkeypatch,
    path,
    service_name,
    provider_value,
    has_data,
):
    monkeypatch.setattr(toz.toz_service, service_name, lambda currency, days: provider_value)

    response = client.get(path)

    assert response.status_code == 200
    assert ("data" in response.json()) is has_data
    if has_data:
        assert response.json()["data"] == []


@pytest.mark.parametrize("path", ["/toz/gold/history", "/toz/silver/history"])
def test_history_endpoints_reject_non_integer_days(path):
    response = client.get(path, params={"days": "many"})

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("service_name", "path"),
    [
        ("get_gold_quote", "/toz/gold/quote"),
        ("get_gold_history", "/toz/gold/history"),
        ("get_silver_quote", "/toz/silver/quote"),
        ("get_silver_history", "/toz/silver/history"),
    ],
)
def test_precious_metal_provider_failures_return_public_500_envelopes(monkeypatch, service_name, path):
    def fail(*args, **kwargs):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(toz.toz_service, service_name, fail)

    response = client.get(path)

    assert response.status_code == 500
    assert response.json()["status"] == 500
    assert "data" not in response.json()
