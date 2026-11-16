from unittest.mock import patch

import pandas as pd
import pydantic
import pytest

from app.services import toz

GOLD_INFO = {
    "currency": "USD",
    "regularMarketPrice": 2650.0,
    "regularMarketChange": 15.0,
    "regularMarketChangePercent": 0.57,
    "regularMarketOpen": 2640.0,
    "regularMarketDayHigh": 2660.0,
    "regularMarketDayLow": 2635.0,
    "fiftyTwoWeekHigh": 2800.0,
    "fiftyTwoWeekLow": 2100.0,
    "regularMarketVolume": 50_000,
}

SILVER_INFO = {
    "currency": "USD",
    "regularMarketPrice": 31.5,
    "regularMarketChange": 0.3,
    "regularMarketChangePercent": 0.96,
    "regularMarketOpen": 31.2,
    "regularMarketDayHigh": 31.8,
    "regularMarketDayLow": 31.0,
    "fiftyTwoWeekHigh": 35.0,
    "fiftyTwoWeekLow": 22.0,
    "regularMarketVolume": 80_000,
}

FX_INFO = {
    "currency": "AUD",
    "regularMarketPrice": 1.55,
}


def _history_frame(closes):
    dates = pd.date_range("2026-01-01", periods=len(closes), freq="D", tz="America/New_York")
    return pd.DataFrame(
        {
            "Open": closes,
            "High": [value + 5.0 for value in closes],
            "Low": [value - 5.0 for value in closes],
            "Close": [value + 2.0 for value in closes],
            "Volume": [1_000 + i for i in range(len(closes))],
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
        self._history = history_data if history_data is not None else _history_frame([100.0])
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


def _provider_patch(
    commodity_info,
    *,
    history_data=None,
    histories=None,
    history_error=None,
    fx_info=FX_INFO,
):
    commodity_ticker = FakeTicker(
        commodity_info,
        history_data,
        histories=histories,
        history_error=history_error,
    )
    fx_ticker = FakeTicker(fx_info)

    def ticker_boundary(symbol):
        return fx_ticker if symbol.endswith("=X") else commodity_ticker

    return patch("app.services.toz.yf.Ticker", side_effect=ticker_boundary)


@pytest.mark.parametrize(
    ("service_function", "commodity_info", "expected_price"),
    [
        (toz.get_gold_quote, GOLD_INFO, 2650.0),
        (toz.get_silver_quote, SILVER_INFO, 31.5),
    ],
)
def test_quotes_return_usd_models_by_default(service_function, commodity_info, expected_price):
    with _provider_patch(commodity_info):
        result = service_function()

    assert result is not None
    assert result.currency == "USD"
    assert result.market_price == expected_price


@pytest.mark.parametrize(
    ("service_function", "commodity_info"),
    [
        (toz.get_gold_quote, GOLD_INFO),
        (toz.get_silver_quote, SILVER_INFO),
    ],
)
def test_empty_currency_uses_usd_for_quotes(service_function, commodity_info):
    with _provider_patch(commodity_info):
        result = service_function("")

    assert result is not None
    assert result.currency == "USD"


@pytest.mark.parametrize(
    ("service_function", "commodity_info"),
    [
        (toz.get_gold_quote, GOLD_INFO),
        (toz.get_silver_quote, SILVER_INFO),
    ],
)
def test_quote_currency_is_normalized_and_converted(service_function, commodity_info):
    with _provider_patch(commodity_info):
        result = service_function("aud")

    assert result is not None
    assert result.currency == "AUD"
    assert result.market_price == pytest.approx(commodity_info["regularMarketPrice"] * 1.55)


@pytest.mark.parametrize(
    ("service_function", "commodity_info"),
    [
        (toz.get_gold_quote, GOLD_INFO),
        (toz.get_silver_quote, SILVER_INFO),
    ],
)
def test_quote_returns_none_for_unsupported_currency(service_function, commodity_info):
    with _provider_patch(commodity_info, fx_info={}):
        result = service_function("XYZ")

    assert result is None


@pytest.mark.parametrize("service_function", [toz.get_gold_history, toz.get_silver_history])
def test_histories_preserve_provider_order_and_use_usd_by_default(service_function):
    history = _history_frame([100.0, 95.0, 110.0])

    with _provider_patch({}, history_data=history):
        result = service_function()

    assert result is not None
    assert [point.currency for point in result] == ["USD", "USD", "USD"]
    assert [point.open for point in result] == [100.0, 95.0, 110.0]
    assert [point.close for point in result] == [102.0, 97.0, 112.0]


@pytest.mark.parametrize("service_function", [toz.get_gold_history, toz.get_silver_history])
def test_empty_currency_uses_usd_for_histories(service_function):
    history = _history_frame([100.0, 101.0])

    with _provider_patch({}, history_data=history):
        result = service_function("")

    assert result is not None
    assert [point.currency for point in result] == ["USD", "USD"]


@pytest.mark.parametrize("service_function", [toz.get_gold_history, toz.get_silver_history])
def test_history_currency_is_normalized_and_converted(service_function):
    history = _history_frame([100.0, 101.0])

    with _provider_patch({}, history_data=history):
        result = service_function("aud")

    assert result is not None
    assert [point.currency for point in result] == ["AUD", "AUD"]
    assert result[0].open == pytest.approx(100.0 * 1.55)
    assert result[1].close == pytest.approx(103.0 * 1.55)


@pytest.mark.parametrize("service_function", [toz.get_gold_history, toz.get_silver_history])
def test_empty_provider_history_returns_an_empty_list(service_function):
    empty_history = _history_frame([])

    with _provider_patch({}, history_data=empty_history):
        result = service_function()

    assert result == []


@pytest.mark.parametrize("service_function", [toz.get_gold_history, toz.get_silver_history])
@pytest.mark.parametrize(
    ("num_days", "expected_open"),
    [
        (30, 30.0),
        (0, 30.0),
        (-5, 30.0),
        (500, 500.0),
    ],
)
def test_history_uses_requested_or_default_day_window(
    service_function,
    num_days,
    expected_open,
):
    histories = {
        "30d": _history_frame([30.0]),
        "500d": _history_frame([500.0]),
    }

    with _provider_patch({}, histories=histories):
        result = service_function("USD", num_days)

    assert result is not None
    assert [point.open for point in result] == [expected_open]


@pytest.mark.parametrize("service_function", [toz.get_gold_history, toz.get_silver_history])
def test_history_returns_none_for_unsupported_currency(service_function):
    with _provider_patch({}, fx_info={}):
        result = service_function("XYZ")

    assert result is None


@pytest.mark.parametrize(
    "service_function",
    [
        toz.get_gold_quote,
        toz.get_gold_history,
        toz.get_silver_quote,
        toz.get_silver_history,
    ],
)
def test_provider_failures_propagate(service_function):
    with (
        patch("app.services.toz.yf.Ticker", side_effect=RuntimeError("provider unavailable")),
        pytest.raises(RuntimeError),
    ):
        service_function()


@pytest.mark.parametrize(
    "service_function",
    [
        toz.get_gold_quote,
        toz.get_gold_history,
        toz.get_silver_quote,
        toz.get_silver_history,
    ],
)
def test_currency_metadata_failures_propagate(service_function):
    def ticker_boundary(symbol):
        return FailingInfoTicker() if symbol.endswith("=X") else FakeTicker({})

    with (
        patch("app.services.toz.yf.Ticker", side_effect=ticker_boundary),
        pytest.raises(RuntimeError),
    ):
        service_function("AUD")


@pytest.mark.parametrize("service_function", [toz.get_gold_history, toz.get_silver_history])
def test_history_provider_failures_propagate(service_function):
    with (
        _provider_patch({}, history_error=RuntimeError("history unavailable")),
        pytest.raises(RuntimeError),
    ):
        service_function()


@pytest.mark.parametrize(
    "service_function",
    [
        toz.get_gold_quote,
        toz.get_gold_history,
        toz.get_silver_quote,
        toz.get_silver_history,
    ],
)
def test_invalid_external_fx_rate_is_surfaced(service_function):
    invalid_fx_info = {
        "currency": "AUD",
        "regularMarketPrice": "not-a-rate",
    }

    with (
        _provider_patch({}, fx_info=invalid_fx_info),
        pytest.raises(ValueError),
    ):
        service_function("AUD")


@pytest.mark.parametrize(
    ("service_function", "commodity_info"),
    [
        (toz.get_gold_quote, GOLD_INFO),
        (toz.get_silver_quote, SILVER_INFO),
    ],
)
def test_quote_model_validation_failures_propagate(service_function, commodity_info):
    invalid_info = {
        **commodity_info,
        "regularMarketPrice": "not-a-number",
    }

    with _provider_patch(invalid_info), pytest.raises(pydantic.ValidationError):
        service_function()


@pytest.mark.parametrize("service_function", [toz.get_gold_history, toz.get_silver_history])
def test_history_model_validation_failures_propagate(service_function):
    invalid_history = _history_frame([100.0])
    invalid_history["Open"] = ["not-a-number"]

    with _provider_patch({}, history_data=invalid_history), pytest.raises(pydantic.ValidationError):
        service_function()
