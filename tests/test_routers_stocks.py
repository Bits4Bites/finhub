import json
import types

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import market_data as models_market_data
from app.models import stocks as models_stocks
from app.routers import stocks

client = TestClient(app)


def _quote(price: float = 100.0, currency: str = "AUD") -> models_market_data.StockQuote:
    ticker = types.SimpleNamespace(
        info={
            "currency": currency,
            "regularMarketPrice": price,
        }
    )
    return models_market_data.StockQuote(ticker)


def _history_point(symbol: str, marker: float, timestamp_str: str | None = None) -> models_market_data.HistoryPoint:
    return models_market_data.HistoryPoint(
        timestamp=1_735_689_600,
        timestamp_str=timestamp_str or symbol,
        close=marker,
    )


def _stock_ticker(symbol: str) -> types.SimpleNamespace:
    history = pd.DataFrame(
        {
            "Open": [100.0] * 30,
            "High": [101.0] * 30,
            "Low": [99.0] * 30,
            "Close": [100.0] * 30,
            "Volume": [1_000] * 30,
            "Dividends": [0.0] * 30,
        },
        index=pd.date_range("2025-01-01", periods=30, freq="B", tz="UTC"),
    )
    return types.SimpleNamespace(
        info={
            "symbol": symbol,
            "currency": "AUD",
            "fullExchangeName": "ASX",
            "country": "Australia",
            "shortName": symbol,
            "longName": f"{symbol} Limited",
            "quoteType": "EQUITY",
            "regularMarketPrice": 100.0,
        },
        history=lambda **_kwargs: history.copy(),
    )


def test_quotes_normalize_trim_and_deduplicate_symbols_in_first_seen_order(monkeypatch):
    def fake_quotes(symbols):
        return {symbol: _quote(100 + index) for index, symbol in enumerate(symbols)}

    monkeypatch.setattr(stocks.stock_service, "get_stock_quotes", fake_quotes)

    response = client.get(
        "/stocks/quotes",
        params={"symbols": " cba.ax, BHP.AX , cba.ax "},
    )

    assert response.status_code == 200
    assert response.json()["status"] == 200
    assert response.json()["data"] == {
        "CBA.AX": {"currency": "AUD", "market_price": 100.0},
        "BHP.AX": {"currency": "AUD", "market_price": 101.0},
    }


def test_quotes_omit_symbols_not_returned_by_the_provider(monkeypatch):
    monkeypatch.setattr(
        stocks.stock_service,
        "get_stock_quotes",
        lambda symbols: {symbols[0]: _quote()},
    )

    response = client.get("/stocks/quotes", params={"symbols": "CBA.AX,BHP.AX"})

    assert response.status_code == 200
    assert list(response.json()["data"]) == ["CBA.AX"]


@pytest.mark.parametrize("symbols", [None, "", "   ", ",", "CBA.AX,,BHP.AX", "CBA.AX,"])
def test_quotes_reject_missing_or_empty_symbol_entries(symbols):
    params = {} if symbols is None else {"symbols": symbols}

    response = client.get("/stocks/quotes", params=params)

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("path_suffix", "service_name", "model_type"),
    [
        ("overview", "get_symbol_overview", models_stocks.SymbolOverview),
        ("info", "get_symbol_info", models_stocks.SymbolInfo),
    ],
)
def test_symbol_details_normalize_the_path_symbol_and_return_provider_data(
    monkeypatch,
    path_suffix,
    service_name,
    model_type,
):
    def fake_lookup(symbol):
        return model_type(_stock_ticker(symbol))

    monkeypatch.setattr(stocks.stock_service, service_name, fake_lookup)

    response = client.get(f"/stocks/ cba.ax /{path_suffix}")

    assert response.status_code == 200
    assert response.json()["data"]["short_name"] == "CBA.AX"


@pytest.mark.parametrize(
    ("path_suffix", "service_name"),
    [
        ("overview", "get_symbol_overview"),
        ("info", "get_symbol_info"),
    ],
)
def test_missing_symbol_details_use_application_level_404(monkeypatch, path_suffix, service_name):
    monkeypatch.setattr(stocks.stock_service, service_name, lambda symbol: None)

    response = client.get(f"/stocks/UNKNOWN/{path_suffix}")

    assert response.status_code == 200
    assert response.json()["status"] == 404
    assert "data" not in response.json()


def test_quote_at_date_normalizes_inputs_and_returns_the_selected_observation(monkeypatch):
    def fake_quote(symbol, date_str):
        return _history_point(symbol, 105.0, f"{symbol}|{date_str}")

    monkeypatch.setattr(stocks.stock_service, "get_stock_quote_at_date", fake_quote)

    response = client.get("/stocks/cba.ax/quote_at/2025-01-15")

    assert response.status_code == 200
    assert response.json()["data"]["timestamp_str"] == "CBA.AX|2025-01-15"
    assert response.json()["data"]["close"] == 105.0


@pytest.mark.parametrize(
    "date_str",
    ["not-a-date", "2025-1-15", "2025-01-5", "2025-02-29", "20250115"],
)
def test_quote_at_date_rejects_non_calendar_or_non_fixed_width_dates(date_str):
    response = client.get(f"/stocks/CBA.AX/quote_at/{date_str}")

    assert response.status_code == 422
    assert response.json()["status"] == 422


def test_quote_at_date_can_return_the_prior_trading_observation(monkeypatch):
    monkeypatch.setattr(
        stocks.stock_service,
        "get_stock_quote_at_date",
        lambda symbol, date_str: _history_point(symbol, 104.0, "2025-01-17 00:00:00"),
    )

    response = client.get("/stocks/CBA.AX/quote_at/2025-01-19")

    assert response.status_code == 200
    assert response.json()["data"]["timestamp_str"] == "2025-01-17 00:00:00"


def test_quote_at_date_uses_application_level_404_when_no_observation_exists(monkeypatch):
    monkeypatch.setattr(stocks.stock_service, "get_stock_quote_at_date", lambda symbol, date_str: None)

    response = client.get("/stocks/CBA.AX/quote_at/2025-01-15")

    assert response.status_code == 200
    assert response.json()["status"] == 404
    assert "data" not in response.json()


@pytest.mark.parametrize(
    ("observation_date", "expected_application_status"),
    [
        ("2025-01-01", 200),
        ("2024-12-31", 404),
    ],
)
def test_quote_at_date_uses_the_inclusive_preceding_fourteen_day_window(
    monkeypatch,
    observation_date,
    expected_application_status,
):
    history = pd.DataFrame(
        {
            "Open": [100.0],
            "High": [101.0],
            "Low": [99.0],
            "Close": [100.5],
            "Volume": [1_000],
            "Dividends": [0.0],
        },
        index=pd.DatetimeIndex([observation_date], tz="UTC"),
    )
    ticker = types.SimpleNamespace(
        info={"quoteType": "EQUITY"},
        history=lambda **_kwargs: history.copy(),
    )
    monkeypatch.setattr(stocks.stock_service.yf, "Ticker", lambda symbol: ticker)

    response = client.get("/stocks/CBA.AX/quote_at/2025-01-15")

    assert response.status_code == 200
    assert response.json()["status"] == expected_application_status
    if expected_application_status == 200:
        assert response.json()["data"]["timestamp_str"].startswith("2025-01-01")
    else:
        assert "data" not in response.json()


@pytest.mark.parametrize(("days", "expected_days"), [(None, 100), (30, 30), (0, 100), (-7, 100)])
def test_history_normalizes_symbol_and_documented_day_defaults(monkeypatch, days, expected_days):
    def fake_history(symbol, requested_days):
        return [_history_point(symbol, float(requested_days))]

    monkeypatch.setattr(stocks.stock_service, "get_symbol_history", fake_history)
    params = {} if days is None else {"days": days}

    response = client.get("/stocks/cba.ax/history", params=params)

    assert response.status_code == 200
    assert response.json()["data"][0]["timestamp_str"] == "CBA.AX"
    assert response.json()["data"][0]["close"] == expected_days


@pytest.mark.parametrize(("provider_value", "has_data"), [([], True), (None, False)])
def test_history_preserves_empty_and_unavailable_provider_outcomes(monkeypatch, provider_value, has_data):
    monkeypatch.setattr(stocks.stock_service, "get_symbol_history", lambda symbol, days: provider_value)

    response = client.get("/stocks/CBA.AX/history", params={"days": 30})

    assert response.status_code == 200
    assert ("data" in response.json()) is has_data
    if has_data:
        assert response.json()["data"] == []


def test_history_rejects_non_integer_days():
    response = client.get("/stocks/CBA.AX/history", params={"days": "thirty"})

    assert response.status_code == 422


def test_index_companies_normalize_index_and_preserve_published_order(monkeypatch):
    market_indices = stocks.market_service.MarketIndexStore()
    market_indices.load(
        "ASX20",
        json.dumps(
            {
                "data": [
                    {
                        "symbol": "CBA.AX",
                        "company": "Commonwealth Bank",
                        "sector": "Financials",
                        "market_cap": 200_000_000_000,
                    },
                    {
                        "symbol": "BHP.AX",
                        "company": "BHP Group",
                        "sector": "Materials",
                        "market_cap": 100_000_000_000,
                    },
                ]
            }
        ),
    )
    monkeypatch.setattr(stocks.market_service, "market_indices", market_indices)

    response = client.get("/stocks/index/ asx20 /companies")

    assert response.status_code == 200
    assert [company["symbol"] for company in response.json()["data"]] == ["CBA.AX", "BHP.AX"]


@pytest.mark.parametrize("load_empty_index", [False, True])
def test_unknown_or_empty_index_returns_an_empty_company_list(monkeypatch, load_empty_index):
    market_indices = stocks.market_service.MarketIndexStore()
    if load_empty_index:
        market_indices.load("ASX20", json.dumps({"data": []}))
    monkeypatch.setattr(stocks.market_service, "market_indices", market_indices)

    response = client.get("/stocks/index/ASX20/companies")

    assert response.status_code == 200
    assert response.json()["data"] == []


@pytest.mark.parametrize("provider_value", [{"long_name": "Apple Inc."}, {}, None])
def test_info_debug_preserves_raw_provider_outcomes(monkeypatch, provider_value):
    monkeypatch.setattr(
        stocks.stock_service,
        "get_symbol_info_raw",
        lambda symbol: {**provider_value, "requested_symbol": symbol} if isinstance(provider_value, dict) else None,
    )

    response = client.get("/stocks/aapl/info_debug")

    assert response.status_code == 200
    if provider_value is None:
        assert "data" not in response.json()
    else:
        assert response.json()["data"]["requested_symbol"] == "AAPL"


@pytest.mark.parametrize(
    ("target", "path", "params"),
    [
        ("get_stock_quotes", "/stocks/quotes", {"symbols": "AAPL"}),
        ("get_symbol_overview", "/stocks/AAPL/overview", None),
        ("get_symbol_info", "/stocks/AAPL/info", None),
        ("get_symbol_history", "/stocks/AAPL/history", None),
        ("get_stock_quote_at_date", "/stocks/AAPL/quote_at/2025-01-15", None),
        ("get_symbol_info_raw", "/stocks/AAPL/info_debug", None),
    ],
)
def test_stock_provider_failures_return_public_500_envelopes(monkeypatch, target, path, params):
    def fail(*args, **kwargs):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(stocks.stock_service, target, fail)

    response = client.get(path, params=params)

    assert response.status_code == 500
    assert response.json()["status"] == 500
    assert "data" not in response.json()
