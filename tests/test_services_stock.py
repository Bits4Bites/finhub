from unittest.mock import patch

import pandas as pd
import pydantic
import pytest

from app.services import stock

EQUITY_INFO = {
    "quoteType": "EQUITY",
    "symbol": "AAPL",
    "currency": "USD",
    "fullExchangeName": "NasdaqGS",
    "country": "United States",
    "regularMarketPrice": 195.0,
    "regularMarketChange": 2.5,
    "regularMarketChangePercent": 1.3,
    "regularMarketOpen": 193.0,
    "regularMarketDayHigh": 196.0,
    "regularMarketDayLow": 192.0,
    "fiftyTwoWeekHigh": 210.0,
    "fiftyTwoWeekLow": 140.0,
    "regularMarketVolume": 50_000_000,
    "shortName": "Apple Inc.",
    "longName": "Apple Inc.",
    "sector": "Technology",
    "industry": "Consumer Electronics",
    "longBusinessSummary": "Apple designs consumer electronics.",
    "marketCap": 3_000_000_000_000,
    "dividendRate": 1.0,
    "dividendYield": 0.005,
}

ETF_INFO = {
    "quoteType": "ETF",
    "symbol": "SPY",
    "currency": "USD",
    "fullExchangeName": "NYSEArca",
    "country": "United States",
    "regularMarketPrice": 450.0,
    "regularMarketChange": 1.0,
    "regularMarketChangePercent": 0.22,
    "regularMarketOpen": 449.0,
    "regularMarketDayHigh": 451.0,
    "regularMarketDayLow": 448.0,
    "fiftyTwoWeekHigh": 480.0,
    "fiftyTwoWeekLow": 380.0,
    "regularMarketVolume": 80_000_000,
    "shortName": "SPDR S&P 500 ETF Trust",
    "longName": "SPDR S&P 500 ETF Trust",
    "sector": "",
    "industry": "",
    "marketCap": 400_000_000_000,
}

MUTUAL_FUND_INFO = {
    **ETF_INFO,
    "quoteType": "MUTUALFUND",
    "symbol": "VTSAX",
    "fullExchangeName": "NASDAQ",
    "shortName": "Vanguard Total Stock Market Fund",
    "longName": "Vanguard Total Stock Market Fund",
}

UNSUPPORTED_INFO = {
    "quoteType": "CURRENCY",
    "symbol": "EURUSD=X",
    "currency": "USD",
}

MISSING_QUOTE_TYPE_INFO = {
    "quoteType": None,
    "symbol": "FAKE",
    "currency": "USD",
}


def _history_frame(num_rows=220, *, start="2025-01-01", base=100.0):
    dates = pd.date_range(start, periods=num_rows, freq="D", tz="America/New_York")
    return pd.DataFrame(
        {
            "Open": [base + i for i in range(num_rows)],
            "High": [base + 5.0 + i for i in range(num_rows)],
            "Low": [base - 5.0 + i for i in range(num_rows)],
            "Close": [base + 2.0 + i for i in range(num_rows)],
            "Volume": [1_000_000 + i * 1_000 for i in range(num_rows)],
            "Dividends": [0.0] * num_rows,
        },
        index=dates,
    )


def _history_from_closes(closes, *, start="2026-01-01"):
    dates = pd.date_range(start, periods=len(closes), freq="D", tz="America/New_York")
    return pd.DataFrame(
        {
            "Open": closes,
            "High": [value + 1.0 for value in closes],
            "Low": [value - 1.0 for value in closes],
            "Close": closes,
            "Volume": [1_000_000 + i for i in range(len(closes))],
            "Dividends": [0.0] * len(closes),
        },
        index=dates,
    )


class FakeTicker:
    def __init__(
        self,
        info,
        history_data=None,
        *,
        histories=None,
        history_error=None,
    ):
        self.info = info
        self._history = history_data if history_data is not None else _history_frame()
        self._histories = histories or {}
        self._history_error = history_error

    def history(self, *, period=None, **_kwargs):
        if self._history_error is not None:
            raise self._history_error
        return self._histories.get(period, self._history).copy()


class FailingInfoTicker:
    @property
    def info(self):
        raise RuntimeError("metadata unavailable")


class FakeTickerCollection:
    def __init__(self, tickers):
        self.tickers = tickers


def _ticker_patch(tickers):
    return patch(
        "app.services.stock.yf.Ticker",
        side_effect=lambda symbol: tickers[symbol],
    )


def test_resolve_symbol_returns_provider_and_canonical_identity():
    info = {
        **ETF_INFO,
        "symbol": "SGOV",
        "regularMarketPrice": 100.65,
        "longName": "iShares 0-3 Month Treasury Bond ETF",
    }

    with _ticker_patch({"SGOV": FakeTicker(info)}):
        result = stock.resolve_symbol("NYSE:SGOV")

    assert result.symbol == "SGOV"
    assert result.normalized_symbol == "NYSE:SGOV"
    assert result.exchange == "NYSE"
    assert result.country == "US"
    assert result.currency == "USD"
    assert result.quote_type == "ETF"
    assert result.company_name == "iShares 0-3 Month Treasury Bond ETF"
    assert result.market_price == 100.65


def test_resolve_symbol_prefers_a_positive_current_price_fallback():
    info = {
        **EQUITY_INFO,
        "symbol": "ACME",
        "regularMarketPrice": 0,
        "currentPrice": 123.45,
    }

    with _ticker_patch({"ACME": FakeTicker(info)}):
        result = stock.resolve_symbol("ACME")

    assert result.market_price == 123.45


def test_resolve_symbol_defaults_country_and_rejects_unusable_prices():
    info = {
        **EQUITY_INFO,
        "country": None,
        "regularMarketPrice": 0,
        "currentPrice": float("nan"),
    }

    with _ticker_patch({"AAPL": FakeTicker(info)}):
        result = stock.resolve_symbol("AAPL")

    assert result.country == "US"
    assert result.market_price is None


@pytest.mark.parametrize(
    "service_call",
    [
        lambda: stock.resolve_symbol("AAPL"),
        lambda: stock.get_symbol_info_raw("AAPL"),
        lambda: stock.get_symbol_info("AAPL"),
        lambda: stock.get_symbol_overview("AAPL"),
        lambda: stock.get_stock_quote_at_date("AAPL", "2026-01-01"),
        lambda: stock.get_symbol_history("AAPL"),
    ],
)
def test_single_symbol_provider_failures_propagate(service_call):
    with (
        patch("app.services.stock.yf.Ticker", side_effect=RuntimeError("provider unavailable")),
        pytest.raises(RuntimeError),
    ):
        service_call()


@pytest.mark.parametrize(
    "service_call",
    [
        lambda: stock.resolve_symbol("AAPL"),
        lambda: stock.get_symbol_info_raw("AAPL"),
        lambda: stock.get_symbol_info("AAPL"),
        lambda: stock.get_symbol_overview("AAPL"),
        lambda: stock.get_stock_quote_at_date("AAPL", "2026-01-01"),
        lambda: stock.get_symbol_history("AAPL"),
    ],
)
def test_single_symbol_metadata_failures_propagate(service_call):
    with (
        patch("app.services.stock.yf.Ticker", return_value=FailingInfoTicker()),
        pytest.raises(RuntimeError),
    ):
        service_call()


@pytest.mark.parametrize(
    "service_call",
    [
        lambda: stock.resolve_symbol("ASX:CBA"),
        lambda: stock.get_symbol_info("ASX:CBA"),
        lambda: stock.get_symbol_overview("ASX:CBA"),
        lambda: stock.get_stock_quotes(["ASX:CBA"]),
        lambda: stock.get_stock_quote_at_date("ASX:CBA", "2026-01-01"),
        lambda: stock.get_symbol_history("ASX:CBA"),
    ],
)
def test_symbol_conversion_failures_propagate(service_call):
    with (
        patch(
            "app.services.stock.conv.to_yf_symbol_format",
            side_effect=RuntimeError("conversion unavailable"),
        ),
        pytest.raises(RuntimeError),
    ):
        service_call()


@pytest.mark.parametrize(
    "service_call",
    [
        lambda: stock.get_symbol_info("AAPL"),
        lambda: stock.get_stock_quote_at_date("AAPL", "2026-01-01"),
        lambda: stock.get_symbol_history("AAPL"),
    ],
)
def test_history_provider_failures_propagate(service_call):
    ticker = FakeTicker(
        EQUITY_INFO,
        history_error=RuntimeError("history unavailable"),
    )

    with _ticker_patch({"AAPL": ticker}), pytest.raises(RuntimeError):
        service_call()


def test_get_symbol_info_raw_normalizes_field_names_and_preserves_values():
    info = {
        "longName": "Apple Inc.",
        "marketCap": 3_000_000_000_000,
        "already_snake": "unchanged",
    }

    with _ticker_patch({"AAPL": FakeTicker(info)}):
        result = stock.get_symbol_info_raw("AAPL")

    assert result == {
        "long_name": "Apple Inc.",
        "market_cap": 3_000_000_000_000,
        "already_snake": "unchanged",
    }


def test_get_symbol_info_raw_returns_empty_provider_metadata():
    with _ticker_patch({"UNKNOWN": FakeTicker({})}):
        assert stock.get_symbol_info_raw("UNKNOWN") == {}


@pytest.mark.parametrize(
    "info",
    [EQUITY_INFO, ETF_INFO, MUTUAL_FUND_INFO],
    ids=["equity", "etf", "mutual-fund"],
)
def test_get_symbol_info_returns_models_for_supported_types(info):
    symbol = info["symbol"]

    with _ticker_patch({symbol: FakeTicker(info)}):
        result = stock.get_symbol_info(symbol)

    assert result is not None
    assert result.symbol == symbol
    assert result.quote_type == info["quoteType"]
    assert result.stock_quote.market_price == info["regularMarketPrice"]


@pytest.mark.parametrize("info", [UNSUPPORTED_INFO, MISSING_QUOTE_TYPE_INFO])
def test_get_symbol_info_returns_none_for_unsupported_types(info):
    symbol = info["symbol"]

    with _ticker_patch({symbol: FakeTicker(info)}):
        result = stock.get_symbol_info(symbol)

    assert result is None


def test_get_symbol_info_accepts_exchange_qualified_symbols():
    info = {
        **EQUITY_INFO,
        "symbol": "CBA.AX",
        "fullExchangeName": "ASX",
        "country": "Australia",
    }

    with _ticker_patch({"CBA.AX": FakeTicker(info)}):
        result = stock.get_symbol_info("ASX:CBA")

    assert result is not None
    assert result.normalized_symbol == "ASX:CBA"
    assert result.country == "AU"


def test_get_symbol_info_surfaces_model_validation_errors():
    invalid_info = {
        **EQUITY_INFO,
        "regularMarketPrice": "not-a-number",
    }

    with _ticker_patch({"AAPL": FakeTicker(invalid_info)}), pytest.raises(pydantic.ValidationError):
        stock.get_symbol_info("AAPL")


@pytest.mark.parametrize(
    "info",
    [EQUITY_INFO, ETF_INFO, MUTUAL_FUND_INFO],
    ids=["equity", "etf", "mutual-fund"],
)
def test_get_symbol_overview_returns_models_for_supported_types(info):
    symbol = info["symbol"]

    with _ticker_patch({symbol: FakeTicker(info)}):
        result = stock.get_symbol_overview(symbol)

    assert result is not None
    assert result.symbol == symbol
    assert result.quote_type == info["quoteType"]


@pytest.mark.parametrize("info", [UNSUPPORTED_INFO, MISSING_QUOTE_TYPE_INFO])
def test_get_symbol_overview_returns_none_for_unsupported_types(info):
    symbol = info["symbol"]

    with _ticker_patch({symbol: FakeTicker(info)}):
        result = stock.get_symbol_overview(symbol)

    assert result is None


def test_get_symbol_overview_normalizes_exchange_qualified_symbols():
    info = {
        **EQUITY_INFO,
        "symbol": "CBA.AX",
        "fullExchangeName": "ASX",
        "country": "Australia",
    }

    with _ticker_patch({"CBA.AX": FakeTicker(info)}):
        result = stock.get_symbol_overview("ASX:CBA")

    assert result is not None
    assert result.normalized_symbol == "ASX:CBA"


def test_get_symbol_overview_surfaces_model_validation_errors():
    invalid_info = {
        **EQUITY_INFO,
        "symbol": None,
    }

    with _ticker_patch({"AAPL": FakeTicker(invalid_info)}), pytest.raises(pydantic.ValidationError):
        stock.get_symbol_overview("AAPL")


def test_get_stock_quotes_returns_supported_models_under_original_keys():
    cba_info = {
        **EQUITY_INFO,
        "symbol": "CBA.AX",
        "fullExchangeName": "ASX",
        "country": "Australia",
    }
    collection = FakeTickerCollection(
        {
            "AAPL": FakeTicker(EQUITY_INFO),
            "CBA.AX": FakeTicker(cba_info),
            "VTSAX": FakeTicker(UNSUPPORTED_INFO),
        }
    )

    with patch("app.services.stock.yf.Tickers", return_value=collection):
        result = stock.get_stock_quotes(["AAPL", "ASX:CBA", "VTSAX", "MISSING"])

    assert list(result) == ["AAPL", "ASX:CBA"]
    assert result["AAPL"].market_price == 195.0
    assert result["ASX:CBA"].market_price == 195.0


def test_get_stock_quotes_includes_mutual_funds_and_omits_missing_quote_types():
    collection = FakeTickerCollection(
        {
            "VTSAX": FakeTicker(MUTUAL_FUND_INFO),
            "FAKE": FakeTicker(MISSING_QUOTE_TYPE_INFO),
        }
    )

    with patch("app.services.stock.yf.Tickers", return_value=collection):
        result = stock.get_stock_quotes(["VTSAX", "FAKE"])

    assert list(result) == ["VTSAX"]
    assert result["VTSAX"].market_price == 450.0


def test_get_stock_quotes_returns_empty_for_empty_input():
    with patch(
        "app.services.stock.yf.Tickers",
        return_value=FakeTickerCollection({}),
    ):
        result = stock.get_stock_quotes([])

    assert result == {}


def test_get_stock_quotes_surfaces_provider_metadata_and_model_errors():
    with (
        patch("app.services.stock.yf.Tickers", side_effect=RuntimeError("provider unavailable")),
        pytest.raises(RuntimeError),
    ):
        stock.get_stock_quotes(["AAPL"])

    with (
        patch(
            "app.services.stock.yf.Tickers",
            return_value=FakeTickerCollection({"AAPL": FailingInfoTicker()}),
        ),
        pytest.raises(RuntimeError),
    ):
        stock.get_stock_quotes(["AAPL"])

    invalid_info = {
        **EQUITY_INFO,
        "regularMarketPrice": "not-a-number",
    }
    with (
        patch(
            "app.services.stock.yf.Tickers",
            return_value=FakeTickerCollection({"AAPL": FakeTicker(invalid_info)}),
        ),
        pytest.raises(pydantic.ValidationError),
    ):
        stock.get_stock_quotes(["AAPL"])


def test_get_stock_quote_at_date_returns_latest_eligible_observation():
    history = _history_from_closes([102.0, 105.0], start="2026-01-02")
    history.index = pd.DatetimeIndex(["2026-01-02 00:00:00-05:00", "2026-01-05 00:00:00-05:00"])

    with _ticker_patch({"AAPL": FakeTicker(EQUITY_INFO, history)}):
        result = stock.get_stock_quote_at_date("AAPL", "2026-01-04")

    assert result is not None
    assert result.close == 102.0
    assert result.timestamp_str.startswith("2026-01-02")


@pytest.mark.parametrize(
    ("observation_date", "expected_close"),
    [
        ("2026-01-18", 114.0),
        ("2026-01-17", None),
    ],
    ids=["fourteen-days-before", "fifteen-days-before"],
)
def test_get_stock_quote_at_date_enforces_exact_lookback_boundary(
    observation_date,
    expected_close,
):
    history = _history_from_closes([114.0], start=observation_date)

    with _ticker_patch({"AAPL": FakeTicker(EQUITY_INFO, history)}):
        result = stock.get_stock_quote_at_date("AAPL", "2026-02-01")

    if expected_close is None:
        assert result is None
    else:
        assert result is not None
        assert result.close == expected_close


@pytest.mark.parametrize(
    "date_str",
    [
        "not-a-date",
        "2026-1-04",
        "2026-01-4",
        "2026-13-01",
    ],
)
def test_get_stock_quote_at_date_rejects_non_strict_dates(date_str):
    with _ticker_patch({"AAPL": FakeTicker(EQUITY_INFO)}):
        result = stock.get_stock_quote_at_date("AAPL", date_str)

    assert result is None


@pytest.mark.parametrize("info", [ETF_INFO, MUTUAL_FUND_INFO])
def test_get_stock_quote_at_date_supports_fund_types(info):
    history = _history_from_closes([100.0, 101.0], start="2026-01-01")
    symbol = info["symbol"]

    with _ticker_patch({symbol: FakeTicker(info, history)}):
        result = stock.get_stock_quote_at_date(symbol, "2026-01-02")

    assert result is not None
    assert result.close == 101.0


@pytest.mark.parametrize("info", [UNSUPPORTED_INFO, MISSING_QUOTE_TYPE_INFO])
def test_get_stock_quote_at_date_returns_none_for_unsupported_types(info):
    symbol = info["symbol"]

    with _ticker_patch({symbol: FakeTicker(info)}):
        result = stock.get_stock_quote_at_date(symbol, "2026-01-01")

    assert result is None


@pytest.mark.parametrize(
    "history",
    [
        pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume", "Dividends"]),
        _history_from_closes([100.0], start="2026-01-01"),
    ],
    ids=["empty", "outside-lookback"],
)
def test_get_stock_quote_at_date_returns_none_without_eligible_history(history):
    requested_date = "2026-01-01" if history.empty else "2026-02-01"

    with _ticker_patch({"AAPL": FakeTicker(EQUITY_INFO, history)}):
        result = stock.get_stock_quote_at_date("AAPL", requested_date)

    assert result is None


def test_get_stock_quote_at_date_accepts_exchange_qualified_symbols():
    info = {
        **EQUITY_INFO,
        "symbol": "CBA.AX",
        "fullExchangeName": "ASX",
        "country": "Australia",
    }
    history = _history_from_closes([123.0])

    with _ticker_patch({"CBA.AX": FakeTicker(info, history)}):
        result = stock.get_stock_quote_at_date("ASX:CBA", "2026-01-01")

    assert result is not None
    assert result.close == 123.0


def test_get_stock_quote_at_date_surfaces_model_validation_errors():
    history = _history_from_closes([100.0])
    history["Open"] = ["not-a-number"]

    with _ticker_patch({"AAPL": FakeTicker(EQUITY_INFO, history)}), pytest.raises(pydantic.ValidationError):
        stock.get_stock_quote_at_date("AAPL", "2026-01-01")


def test_get_symbol_history_preserves_provider_order():
    history = _history_from_closes([103.0, 99.0, 105.0])

    with _ticker_patch({"AAPL": FakeTicker(EQUITY_INFO, history)}):
        result = stock.get_symbol_history("AAPL", 3)

    assert result is not None
    assert [point.close for point in result] == [103.0, 99.0, 105.0]
    assert [point.timestamp for point in result] == [int(timestamp.timestamp()) for timestamp in history.index]


@pytest.mark.parametrize("info", [ETF_INFO, MUTUAL_FUND_INFO])
def test_get_symbol_history_supports_fund_types(info):
    history = _history_from_closes([100.0, 101.0])
    symbol = info["symbol"]

    with _ticker_patch({symbol: FakeTicker(info, history)}):
        result = stock.get_symbol_history(symbol, 2)

    assert result is not None
    assert [point.close for point in result] == [100.0, 101.0]


@pytest.mark.parametrize(
    ("days", "expected_close"),
    [
        (30, 30.0),
        (0, 100.0),
        (-5, 100.0),
        (500, 500.0),
    ],
)
def test_get_symbol_history_applies_requested_or_default_day_window(days, expected_close):
    ticker = FakeTicker(
        EQUITY_INFO,
        histories={
            "30d": _history_from_closes([30.0]),
            "100d": _history_from_closes([100.0]),
            "500d": _history_from_closes([500.0]),
        },
    )

    with _ticker_patch({"AAPL": ticker}):
        result = stock.get_symbol_history("AAPL", days)

    assert result is not None
    assert [point.close for point in result] == [expected_close]


@pytest.mark.parametrize("info", [UNSUPPORTED_INFO, MISSING_QUOTE_TYPE_INFO])
def test_get_symbol_history_returns_none_for_unsupported_types(info):
    symbol = info["symbol"]

    with _ticker_patch({symbol: FakeTicker(info)}):
        result = stock.get_symbol_history(symbol, 30)

    assert result is None


def test_get_symbol_history_returns_empty_when_provider_has_no_observations():
    empty_history = pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume", "Dividends"])

    with _ticker_patch({"AAPL": FakeTicker(EQUITY_INFO, empty_history)}):
        result = stock.get_symbol_history("AAPL", 30)

    assert result == []


def test_get_symbol_history_accepts_exchange_qualified_symbols():
    info = {
        **EQUITY_INFO,
        "symbol": "CBA.AX",
        "fullExchangeName": "ASX",
        "country": "Australia",
    }
    history = _history_from_closes([123.0, 124.0])

    with _ticker_patch({"CBA.AX": FakeTicker(info, history)}):
        result = stock.get_symbol_history("ASX:CBA", 2)

    assert result is not None
    assert [point.close for point in result] == [123.0, 124.0]


def test_get_symbol_history_surfaces_model_validation_errors():
    history = _history_from_closes([100.0])
    history["Open"] = ["not-a-number"]

    with _ticker_patch({"AAPL": FakeTicker(EQUITY_INFO, history)}), pytest.raises(pydantic.ValidationError):
        stock.get_symbol_history("AAPL", 1)
