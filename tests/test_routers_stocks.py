from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.models.finhub import HistoryPoint, StockQuote, SymbolInfo, SymbolOverview

client = TestClient(app)


# --- GET /stocks/quotes ---


@patch("app.routers.stocks.stock_service.get_stock_quotes")
def test_get_stock_quotes_success(mock_get_quotes):
    quote = StockQuote.model_construct(currency="AUD", market_price=110.5)
    mock_get_quotes.return_value = {"CBA.AX": quote}

    resp = client.get("/stocks/quotes", params={"symbols": "CBA.AX"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == 200
    assert body["message"] == "ok"
    assert "CBA.AX" in body["data"]
    assert body["data"]["CBA.AX"]["market_price"] == 110.5
    mock_get_quotes.assert_called_once_with(["CBA.AX"])


@patch("app.routers.stocks.stock_service.get_stock_quotes")
def test_get_stock_quotes_multiple_symbols(mock_get_quotes):
    mock_get_quotes.return_value = {}

    resp = client.get("/stocks/quotes", params={"symbols": "CBA.AX, BHP.AX"})
    assert resp.status_code == 200
    mock_get_quotes.assert_called_once_with(["CBA.AX", "BHP.AX"])


@patch("app.routers.stocks.stock_service.get_stock_quotes")
def test_get_stock_quotes_uppercases_symbols(mock_get_quotes):
    mock_get_quotes.return_value = {}

    resp = client.get("/stocks/quotes", params={"symbols": "cba.ax"})
    assert resp.status_code == 200
    mock_get_quotes.assert_called_once_with(["CBA.AX"])


def test_get_stock_quotes_missing_param():
    resp = client.get("/stocks/quotes")
    assert resp.status_code == 422


# --- GET /stocks/{symbol}/overview ---


@patch("app.routers.stocks.stock_service.get_symbol_overview")
def test_get_symbol_overview_success(mock_get_overview):
    overview = SymbolOverview.model_construct(short_name="CBA", long_name="Commonwealth Bank")
    mock_get_overview.return_value = overview

    resp = client.get("/stocks/CBA.AX/overview")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == 200
    assert body["message"] == "ok"
    assert body["data"] is not None
    assert body["data"]["short_name"] == "CBA"
    mock_get_overview.assert_called_once_with("CBA.AX")


@patch("app.routers.stocks.stock_service.get_symbol_overview")
def test_get_symbol_overview_not_found(mock_get_overview):
    mock_get_overview.return_value = None

    resp = client.get("/stocks/INVALID/overview")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == 404
    assert body["message"] == "Symbol not found"
    assert body.get("data") is None


# --- GET /stocks/{symbol}/info ---


@patch("app.routers.stocks.stock_service.get_symbol_info")
def test_get_symbol_info_success(mock_get_info):
    info = SymbolInfo.model_construct(short_name="CBA", long_name="Commonwealth Bank")
    mock_get_info.return_value = info

    resp = client.get("/stocks/CBA.AX/info")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == 200
    assert body["message"] == "ok"
    assert body["data"] is not None
    assert body["data"]["short_name"] == "CBA"
    mock_get_info.assert_called_once_with("CBA.AX")


@patch("app.routers.stocks.stock_service.get_symbol_info")
def test_get_symbol_info_not_found(mock_get_info):
    mock_get_info.return_value = None

    resp = client.get("/stocks/INVALID/info")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == 404
    assert body["message"] == "Symbol not found"
    assert body.get("data") is None


# --- GET /stocks/{symbol}/quote_at/{date_str} ---


@patch("app.routers.stocks.stock_service.get_stock_quote_at_date")
def test_get_quote_at_date_success(mock_get_quote):
    history_point = HistoryPoint.model_construct(timestamp=1705276800, timestamp_str="2025-01-15", close=105.0)
    mock_get_quote.return_value = history_point

    resp = client.get("/stocks/CBA.AX/quote_at/2025-01-15")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == 200
    assert body["message"] == "ok"
    assert body["data"] is not None
    assert body["data"]["close"] == 105.0
    mock_get_quote.assert_called_once_with("CBA.AX", "2025-01-15")


@patch("app.routers.stocks.stock_service.get_stock_quote_at_date")
def test_get_quote_at_date_not_found(mock_get_quote):
    mock_get_quote.return_value = None

    resp = client.get("/stocks/CBA.AX/quote_at/2025-01-15")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == 404
    assert body["message"] == "Symbol or quote not found"
    assert body.get("data") is None


# --- GET /stocks/{symbol}/history ---


@patch("app.routers.stocks.stock_service.get_symbol_history")
def test_get_symbol_history_success(mock_get_history):
    points = [
        HistoryPoint.model_construct(timestamp=1705276800, timestamp_str="2025-01-15", close=105.0),
        HistoryPoint.model_construct(timestamp=1705363200, timestamp_str="2025-01-16", close=107.0),
    ]
    mock_get_history.return_value = points

    resp = client.get("/stocks/CBA.AX/history?days=30")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == 200
    assert body["message"] == "ok"
    assert body["data"] is not None
    assert len(body["data"]) == 2
    assert body["data"][0]["close"] == 105.0
    mock_get_history.assert_called_once_with("CBA.AX", 30)


@patch("app.routers.stocks.stock_service.get_symbol_history")
def test_get_symbol_history_defaults_days(mock_get_history):
    mock_get_history.return_value = []

    resp = client.get("/stocks/CBA.AX/history")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == 200
    mock_get_history.assert_called_once_with("CBA.AX", 100)


@patch("app.routers.stocks.stock_service.get_symbol_history")
def test_get_symbol_history_none(mock_get_history):
    mock_get_history.return_value = None

    resp = client.get("/stocks/CBA.AX/history?days=30")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == 200
    assert body["message"] == "ok"
    assert body.get("data") is None


# --- GET /stocks/index/{index}/companies ---


@patch("app.routers.stocks.config.market_indices")
def test_get_index_companies_success(mock_market_indices):
    from app.config import CompanyBriefInfo

    company = CompanyBriefInfo(symbol="CBA.AX", name="Commonwealth Bank", sector="Financials", market_cap=200000000000)
    mock_market_indices.indices = {"ASX20": {"CBA.AX": company}}

    resp = client.get("/stocks/index/ASX20/companies")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == 200
    assert body["message"] == "ok"
    assert len(body["data"]) == 1
    assert body["data"][0]["symbol"] == "CBA.AX"


@patch("app.routers.stocks.config.market_indices")
def test_get_index_companies_uppercases_index(mock_market_indices):
    from app.config import CompanyBriefInfo

    company = CompanyBriefInfo(symbol="BHP.AX", name="BHP Group", sector="Materials", market_cap=100000000000)
    mock_market_indices.indices = {"ASX20": {"BHP.AX": company}}

    resp = client.get("/stocks/index/asx20/companies")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["data"]) == 1


@patch("app.routers.stocks.config.market_indices")
def test_get_index_companies_unknown_index(mock_market_indices):
    mock_market_indices.indices = {}

    resp = client.get("/stocks/index/UNKNOWN/companies")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == 200
    assert body["data"] == []


# --- GET /stocks/{symbol}/info_debug ---


@patch("app.routers.stocks.stock_service.get_symbol_info_raw")
def test_get_symbol_info_debug_success(mock_get_raw):
    mock_get_raw.return_value = {"long_name": "Apple Inc.", "market_cap": 3000000000000}

    resp = client.get("/stocks/AAPL/info_debug")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == 200
    assert body["message"] == "ok"
    assert body["data"]["long_name"] == "Apple Inc."
    mock_get_raw.assert_called_once_with("AAPL")


@patch("app.routers.stocks.stock_service.get_symbol_info_raw")
def test_get_symbol_info_debug_empty(mock_get_raw):
    mock_get_raw.return_value = {}

    resp = client.get("/stocks/INVALID/info_debug")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == 200
    assert body["data"] == {}
