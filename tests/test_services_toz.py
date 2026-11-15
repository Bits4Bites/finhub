from unittest.mock import MagicMock, patch

import pandas as pd
import pydantic
import pytest

from app.services.toz import get_gold_history, get_gold_quote, get_silver_history, get_silver_quote


def _make_ticker_mock(info: dict, history_data: pd.DataFrame = None):
    """Create a mock yf.Ticker with given info and optional history data."""
    ticker = MagicMock()
    ticker.info = info
    if history_data is not None:
        ticker.history = MagicMock(return_value=history_data)
    return ticker


def _make_history_df(num_rows: int = 3) -> pd.DataFrame:
    """Create a sample history DataFrame similar to yfinance output."""
    dates = pd.date_range("2026-01-01", periods=num_rows, freq="D", tz="America/New_York")
    return pd.DataFrame(
        {
            "Open": [100.0 + i for i in range(num_rows)],
            "High": [105.0 + i for i in range(num_rows)],
            "Low": [95.0 + i for i in range(num_rows)],
            "Close": [102.0 + i for i in range(num_rows)],
            "Volume": [1000 + i for i in range(num_rows)],
        },
        index=dates,
    )


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
    "regularMarketVolume": 50000,
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
    "regularMarketVolume": 80000,
}

FX_INFO = {
    "currency": "AUD",
    "regularMarketPrice": 1.55,
}


@pytest.mark.parametrize(
    ("service_func", "commodity_info"),
    [
        (get_gold_quote, GOLD_INFO),
        (get_silver_quote, SILVER_INFO),
    ],
)
def test_empty_currency_uses_usd(service_func, commodity_info):
    with patch("app.services.toz.yf.Ticker") as mock_ticker_cls:
        mock_ticker_cls.return_value = _make_ticker_mock(commodity_info)

        result = service_func("")

    assert result is not None
    assert result.currency == "USD"


@pytest.mark.parametrize(
    ("service_func", "commodity_info"),
    [
        (get_gold_quote, GOLD_INFO),
        (get_silver_quote, SILVER_INFO),
    ],
)
def test_lowercase_currency_is_normalized_for_quotes(service_func, commodity_info):
    fx_ticker = _make_ticker_mock(FX_INFO)
    commodity_ticker = _make_ticker_mock(commodity_info)
    with patch(
        "app.services.toz.yf.Ticker",
        side_effect=[fx_ticker, commodity_ticker],
    ):
        result = service_func("aud")

    assert result is not None
    assert result.currency == "AUD"
    assert result.market_price == pytest.approx(commodity_info["regularMarketPrice"] * 1.55)


@pytest.mark.parametrize("service_func", [get_gold_history, get_silver_history])
def test_empty_provider_history_returns_an_empty_list(service_func):
    empty_history = _make_history_df(0)
    with patch("app.services.toz.yf.Ticker") as mock_ticker_cls:
        mock_ticker_cls.return_value = _make_ticker_mock({}, empty_history)

        result = service_func()

    assert result == []


@pytest.mark.parametrize("service_func", [get_gold_history, get_silver_history])
def test_empty_currency_history_uses_usd(service_func):
    history = _make_history_df(2)
    with patch("app.services.toz.yf.Ticker") as mock_ticker_cls:
        mock_ticker_cls.return_value = _make_ticker_mock({}, history)

        result = service_func("")

    assert result is not None
    assert [point.currency for point in result] == ["USD", "USD"]
    assert result[0].open == history.iloc[0]["Open"]


@pytest.mark.parametrize("service_func", [get_gold_history, get_silver_history])
def test_lowercase_currency_is_normalized_for_histories(service_func):
    history = _make_history_df(2)
    fx_ticker = _make_ticker_mock(FX_INFO)
    commodity_ticker = _make_ticker_mock({}, history)
    with patch(
        "app.services.toz.yf.Ticker",
        side_effect=[fx_ticker, commodity_ticker],
    ):
        result = service_func("aud")

    assert result is not None
    assert [point.currency for point in result] == ["AUD", "AUD"]
    assert result[0].open == pytest.approx(history.iloc[0]["Open"] * 1.55)


@pytest.mark.parametrize(
    "service_func",
    [get_gold_quote, get_gold_history, get_silver_quote, get_silver_history],
)
def test_provider_failures_propagate(service_func):
    with patch("app.services.toz.yf.Ticker", side_effect=RuntimeError("provider unavailable")):
        with pytest.raises(RuntimeError):
            service_func()


@pytest.mark.parametrize(
    "service_func",
    [get_gold_quote, get_gold_history, get_silver_quote, get_silver_history],
)
def test_currency_metadata_failures_propagate(service_func):
    class FailingTicker:
        @property
        def info(self):
            raise RuntimeError("metadata unavailable")

    with patch("app.services.toz.yf.Ticker", return_value=FailingTicker()):
        with pytest.raises(RuntimeError, match="metadata unavailable"):
            service_func("AUD")


@pytest.mark.parametrize("service_func", [get_gold_history, get_silver_history])
def test_history_provider_failures_propagate(service_func):
    ticker = _make_ticker_mock({})
    ticker.history.side_effect = RuntimeError("history unavailable")
    with patch("app.services.toz.yf.Ticker", return_value=ticker):
        with pytest.raises(RuntimeError, match="history unavailable"):
            service_func()


@pytest.mark.parametrize(
    ("service_func", "commodity_info"),
    [
        (get_gold_quote, GOLD_INFO),
        (get_silver_quote, SILVER_INFO),
    ],
)
def test_quote_conversion_failures_propagate(service_func, commodity_info):
    fx_ticker = _make_ticker_mock(FX_INFO)
    commodity_ticker = _make_ticker_mock(commodity_info)
    with (
        patch(
            "app.services.toz.yf.Ticker",
            side_effect=[fx_ticker, commodity_ticker],
        ),
        patch(
            "app.services.toz.models_market_data.StockQuote.to_currency",
            side_effect=RuntimeError("conversion unavailable"),
        ),
        pytest.raises(RuntimeError, match="conversion unavailable"),
    ):
        service_func("AUD")


@pytest.mark.parametrize("service_func", [get_gold_history, get_silver_history])
def test_history_conversion_failures_propagate(service_func):
    history = _make_history_df(1)
    fx_ticker = _make_ticker_mock(FX_INFO)
    commodity_ticker = _make_ticker_mock({}, history)
    with (
        patch(
            "app.services.toz.yf.Ticker",
            side_effect=[fx_ticker, commodity_ticker],
        ),
        patch(
            "app.services.toz.models_market_data.HistoryPoint.to_currency",
            side_effect=RuntimeError("conversion unavailable"),
        ),
        pytest.raises(RuntimeError, match="conversion unavailable"),
    ):
        service_func("AUD")


@pytest.mark.parametrize(
    "service_func",
    [get_gold_quote, get_silver_quote],
)
def test_quote_model_validation_failures_propagate(service_func):
    invalid_info = {
        **GOLD_INFO,
        "regularMarketPrice": "not-a-number",
    }
    with patch(
        "app.services.toz.yf.Ticker",
        return_value=_make_ticker_mock(invalid_info),
    ):
        with pytest.raises(pydantic.ValidationError):
            service_func()


@pytest.mark.parametrize("service_func", [get_gold_history, get_silver_history])
def test_history_model_validation_failures_propagate(service_func):
    invalid_history = _make_history_df(1)
    invalid_history["Open"] = ["not-a-number"]
    with patch(
        "app.services.toz.yf.Ticker",
        return_value=_make_ticker_mock({}, invalid_history),
    ):
        with pytest.raises(pydantic.ValidationError):
            service_func()


class TestGetGoldQuote:
    @patch("app.services.toz.yf.Ticker")
    def test_usd_default(self, mock_ticker_cls):
        mock_ticker_cls.return_value = _make_ticker_mock(GOLD_INFO)
        result = get_gold_quote()
        assert result is not None
        assert result.currency == "USD"
        assert result.market_price == 2650.0

    @patch("app.services.toz.yf.Ticker")
    def test_usd_explicit(self, mock_ticker_cls):
        mock_ticker_cls.return_value = _make_ticker_mock(GOLD_INFO)
        result = get_gold_quote("USD")
        assert result is not None
        assert result.currency == "USD"

    @patch("app.services.toz.yf.Ticker")
    def test_currency_conversion(self, mock_ticker_cls):
        fx_ticker = _make_ticker_mock(FX_INFO)
        gold_ticker = _make_ticker_mock(GOLD_INFO)
        mock_ticker_cls.side_effect = [fx_ticker, gold_ticker]

        result = get_gold_quote("AUD")
        assert result is not None
        assert result.currency == "AUD"
        assert result.market_price == pytest.approx(2650.0 * 1.55)

    @patch("app.services.toz.yf.Ticker")
    def test_unsupported_currency_returns_none(self, mock_ticker_cls):
        # FX ticker without 'currency' key means unsupported
        mock_ticker_cls.return_value = _make_ticker_mock({})
        result = get_gold_quote("XYZ")
        assert result is None


class TestGetGoldHistory:
    @patch("app.services.toz.yf.Ticker")
    def test_usd_default(self, mock_ticker_cls):
        hist_df = _make_history_df(5)
        mock_ticker_cls.return_value = _make_ticker_mock(GOLD_INFO, hist_df)

        result = get_gold_history()
        assert result is not None
        assert len(result) == 5
        assert result[0].currency == "USD"
        assert result[0].open == 100.0

    @patch("app.services.toz.yf.Ticker")
    def test_currency_conversion(self, mock_ticker_cls):
        hist_df = _make_history_df(3)
        fx_ticker = _make_ticker_mock(FX_INFO)
        gold_ticker = _make_ticker_mock(GOLD_INFO, hist_df)
        mock_ticker_cls.side_effect = [fx_ticker, gold_ticker]

        result = get_gold_history("AUD", 7)
        assert result is not None
        assert len(result) == 3
        assert result[0].currency == "AUD"
        assert result[0].open == pytest.approx(100.0 * 1.55)

    @patch("app.services.toz.yf.Ticker")
    def test_unsupported_currency_returns_none(self, mock_ticker_cls):
        mock_ticker_cls.return_value = _make_ticker_mock({})
        result = get_gold_history("XYZ")
        assert result is None

    @patch("app.services.toz.yf.Ticker")
    def test_num_days_clamped_when_zero_or_negative(self, mock_ticker_cls):
        hist_df = _make_history_df(2)
        mock_ticker_cls.return_value = _make_ticker_mock(GOLD_INFO, hist_df)

        get_gold_history("USD", 0)
        # Should use 30d as the period when num_days <= 0
        mock_ticker_cls.return_value.history.assert_called_with(period="30d", interval="1d", auto_adjust=False)

    @patch("app.services.toz.yf.Ticker")
    def test_num_days_over_366_is_not_clamped(self, mock_ticker_cls):
        hist_df = _make_history_df(2)
        mock_ticker_cls.return_value = _make_ticker_mock(GOLD_INFO, hist_df)

        get_gold_history("USD", 500)
        mock_ticker_cls.return_value.history.assert_called_with(period="500d", interval="1d", auto_adjust=False)


class TestGetSilverQuote:
    @patch("app.services.toz.yf.Ticker")
    def test_usd_default(self, mock_ticker_cls):
        mock_ticker_cls.return_value = _make_ticker_mock(SILVER_INFO)
        result = get_silver_quote()
        assert result is not None
        assert result.currency == "USD"
        assert result.market_price == 31.5

    @patch("app.services.toz.yf.Ticker")
    def test_currency_conversion(self, mock_ticker_cls):
        fx_ticker = _make_ticker_mock(FX_INFO)
        silver_ticker = _make_ticker_mock(SILVER_INFO)
        mock_ticker_cls.side_effect = [fx_ticker, silver_ticker]

        result = get_silver_quote("AUD")
        assert result is not None
        assert result.currency == "AUD"
        assert result.market_price == pytest.approx(31.5 * 1.55)

    @patch("app.services.toz.yf.Ticker")
    def test_unsupported_currency_returns_none(self, mock_ticker_cls):
        mock_ticker_cls.return_value = _make_ticker_mock({})
        result = get_silver_quote("XYZ")
        assert result is None


class TestGetSilverHistory:
    @patch("app.services.toz.yf.Ticker")
    def test_usd_default(self, mock_ticker_cls):
        hist_df = _make_history_df(4)
        mock_ticker_cls.return_value = _make_ticker_mock(SILVER_INFO, hist_df)

        result = get_silver_history()
        assert result is not None
        assert len(result) == 4
        assert result[0].currency == "USD"

    @patch("app.services.toz.yf.Ticker")
    def test_currency_conversion(self, mock_ticker_cls):
        hist_df = _make_history_df(2)
        fx_ticker = _make_ticker_mock(FX_INFO)
        silver_ticker = _make_ticker_mock(SILVER_INFO, hist_df)
        mock_ticker_cls.side_effect = [fx_ticker, silver_ticker]

        result = get_silver_history("AUD", 10)
        assert result is not None
        assert len(result) == 2
        assert result[0].currency == "AUD"
        assert result[0].close == pytest.approx(102.0 * 1.55)

    @patch("app.services.toz.yf.Ticker")
    def test_unsupported_currency_returns_none(self, mock_ticker_cls):
        mock_ticker_cls.return_value = _make_ticker_mock({})
        result = get_silver_history("XYZ")
        assert result is None

    @patch("app.services.toz.yf.Ticker")
    def test_num_days_clamped(self, mock_ticker_cls):
        hist_df = _make_history_df(2)
        mock_ticker_cls.return_value = _make_ticker_mock(SILVER_INFO, hist_df)

        get_silver_history("USD", -5)
        mock_ticker_cls.return_value.history.assert_called_with(period="30d", interval="1d", auto_adjust=False)

    @patch("app.services.toz.yf.Ticker")
    def test_num_days_over_366_is_not_clamped(self, mock_ticker_cls):
        hist_df = _make_history_df(2)
        mock_ticker_cls.return_value = _make_ticker_mock(SILVER_INFO, hist_df)

        get_silver_history("USD", 500)
        mock_ticker_cls.return_value.history.assert_called_with(period="500d", interval="1d", auto_adjust=False)
