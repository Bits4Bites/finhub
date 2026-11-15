from unittest.mock import MagicMock, patch

import pandas as pd
import pydantic
import pytest

from app.services.stock import (
    get_stock_quote_at_date,
    get_stock_quotes,
    get_symbol_history,
    get_symbol_info,
    get_symbol_overview,
    resolve_symbol,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
    "regularMarketVolume": 50000000,
    "shortName": "Apple Inc.",
    "longName": "Apple Inc.",
    "sector": "Technology",
    "industry": "Consumer Electronics",
    "longBusinessSummary": "Apple designs consumer electronics.",
    "marketCap": 3000000000000,
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
    "regularMarketVolume": 80000000,
    "shortName": "SPDR S&P 500 ETF Trust",
    "longName": "SPDR S&P 500 ETF Trust",
    "sector": "",
    "industry": "",
    "marketCap": 400000000000,
}

UNSUPPORTED_INFO = {
    "quoteType": "CURRENCY",
    "symbol": "VTSAX",
    "currency": "USD",
}

MUTUAL_FUND_INFO = {
    "quoteType": "MUTUALFUND",
    "symbol": "VTSAX",
    "currency": "USD",
    "fullExchangeName": "NASDAQ",
    "regularMarketPrice": 450.0,
    "regularMarketChange": 1.0,
    "regularMarketChangePercent": 0.22,
    "regularMarketOpen": 449.0,
    "regularMarketDayHigh": 451.0,
    "regularMarketDayLow": 448.0,
    "fiftyTwoWeekHigh": 480.0,
    "fiftyTwoWeekLow": 380.0,
    "regularMarketVolume": 80000000,
    "shortName": "Vanguard Total Stock Market Fund",
    "longName": "Vanguard Total Stock Market Fund",
    "marketCap": 400000000000,
}

NONE_QUOTE_TYPE_INFO = {
    "quoteType": None,
    "symbol": "FAKE",
}


def _make_ticker_mock(info: dict, history_data: pd.DataFrame = None):
    ticker = MagicMock()
    ticker.info = info
    if history_data is None:
        # Provide a default history for models that call ticker.history() during init
        history_data = _make_history_df(5)
    ticker.history = MagicMock(return_value=history_data)
    return ticker


def _make_history_df(num_rows: int = 3) -> pd.DataFrame:
    dates = pd.date_range("2026-01-01", periods=num_rows, freq="D", tz="America/New_York")
    return pd.DataFrame(
        {
            "Open": [100.0 + i for i in range(num_rows)],
            "High": [105.0 + i for i in range(num_rows)],
            "Low": [95.0 + i for i in range(num_rows)],
            "Close": [102.0 + i for i in range(num_rows)],
            "Volume": [1000000 + i * 1000 for i in range(num_rows)],
            "Dividends": [0.0] * num_rows,
        },
        index=dates,
    )


@patch("app.services.stock.yf.Ticker")
def test_resolve_symbol_returns_provider_and_canonical_identity(mock_ticker_cls):
    info = {
        **ETF_INFO,
        "symbol": "SGOV",
        "fullExchangeName": "NYSEArca",
        "regularMarketPrice": 100.65,
        "longName": "iShares 0-3 Month Treasury Bond ETF",
    }
    ticker = _make_ticker_mock(info)
    mock_ticker_cls.side_effect = {"SGOV": ticker}.__getitem__

    result = resolve_symbol("NYSE:SGOV")

    assert result.symbol == "SGOV"
    assert result.normalized_symbol == "NYSE:SGOV"
    assert result.exchange == "NYSE"
    assert result.currency == "USD"
    assert result.quote_type == "ETF"
    assert result.market_price == 100.65


@patch("app.utils.conv.to_yf_symbol_format", return_value="GOVT")
@patch("app.services.stock.yf.Ticker")
def test_resolve_symbol_normalizes_cboe_us_to_nyse(mock_ticker_cls, mock_to_yf):
    info = {
        **ETF_INFO,
        "symbol": "GOVT",
        "exchange": "BTS",
        "fullExchangeName": "Cboe US",
        "regularMarketPrice": 23.45,
        "longName": "iShares U.S. Treasury Bond ETF",
    }
    mock_ticker_cls.return_value = _make_ticker_mock(info)

    result = resolve_symbol("NYSE:GOVT")

    assert result.symbol == "GOVT"
    assert result.normalized_symbol == "NYSE:GOVT"
    assert result.exchange == "NYSE"


@patch("app.utils.conv.to_yf_symbol_format", return_value="ACME")
@patch("app.services.stock.yf.Ticker")
def test_resolve_symbol_uses_current_price_when_regular_price_is_unavailable(mock_ticker_cls, mock_to_yf):
    info = {
        **EQUITY_INFO,
        "symbol": "ACME",
        "regularMarketPrice": 0,
        "currentPrice": 123.45,
    }
    mock_ticker_cls.return_value = _make_ticker_mock(info)

    result = resolve_symbol("ACME")

    assert result.market_price == 123.45


@patch("app.services.stock.yf.Ticker")
def test_resolve_symbol_defaults_country_and_rejects_unusable_prices(mock_ticker_cls):
    info = {
        **EQUITY_INFO,
        "country": None,
        "regularMarketPrice": 0,
        "currentPrice": float("nan"),
    }
    mock_ticker_cls.return_value = _make_ticker_mock(info)

    result = resolve_symbol("AAPL")

    assert result.country == "US"
    assert result.market_price is None


@pytest.mark.parametrize(
    "service_call",
    [
        lambda: resolve_symbol("AAPL"),
        lambda: get_symbol_info("AAPL"),
        lambda: get_symbol_overview("AAPL"),
        lambda: get_stock_quote_at_date("AAPL", "2026-01-01"),
        lambda: get_symbol_history("AAPL"),
    ],
)
@patch("app.services.stock.yf.Ticker", side_effect=RuntimeError("provider unavailable"))
def test_single_symbol_provider_failures_propagate(mock_ticker_cls, service_call):
    with pytest.raises(RuntimeError):
        service_call()


@pytest.mark.parametrize(
    "service_call",
    [
        lambda: resolve_symbol("AAPL"),
        lambda: get_symbol_info("AAPL"),
        lambda: get_symbol_overview("AAPL"),
        lambda: get_stock_quote_at_date("AAPL", "2026-01-01"),
        lambda: get_symbol_history("AAPL"),
    ],
)
@patch("app.services.stock.yf.Ticker")
def test_single_symbol_metadata_failures_propagate(mock_ticker_cls, service_call):
    class FailingTicker:
        @property
        def info(self):
            raise RuntimeError("metadata unavailable")

    mock_ticker_cls.return_value = FailingTicker()

    with pytest.raises(RuntimeError, match="metadata unavailable"):
        service_call()


@pytest.mark.parametrize(
    "service_call",
    [
        lambda: get_symbol_info("AAPL"),
        lambda: get_stock_quote_at_date("AAPL", "2026-01-01"),
        lambda: get_symbol_history("AAPL"),
    ],
)
@patch("app.services.stock.yf.Ticker")
def test_history_provider_failures_propagate(mock_ticker_cls, service_call):
    ticker = _make_ticker_mock(EQUITY_INFO)
    ticker.history.side_effect = RuntimeError("history unavailable")
    mock_ticker_cls.return_value = ticker

    with pytest.raises(RuntimeError, match="history unavailable"):
        service_call()


@pytest.mark.parametrize(
    "service_call",
    [
        lambda: resolve_symbol("ASX:CBA"),
        lambda: get_symbol_info("ASX:CBA"),
        lambda: get_symbol_overview("ASX:CBA"),
        lambda: get_stock_quotes(["ASX:CBA"]),
        lambda: get_stock_quote_at_date("ASX:CBA", "2026-01-01"),
        lambda: get_symbol_history("ASX:CBA"),
    ],
)
@patch(
    "app.services.stock.conv.to_yf_symbol_format",
    side_effect=RuntimeError("conversion unavailable"),
)
def test_symbol_conversion_failures_propagate(mock_conversion, service_call):
    with pytest.raises(RuntimeError, match="conversion unavailable"):
        service_call()


# ---------------------------------------------------------------------------
# get_symbol_info
# ---------------------------------------------------------------------------


class TestGetSymbolInfo:
    @patch("app.utils.conv.to_yf_symbol_format", return_value="AAPL")
    @patch("app.services.stock.yf.Ticker")
    def test_returns_symbol_info_for_equity(self, mock_ticker_cls, mock_to_yf):
        mock_ticker_cls.return_value = _make_ticker_mock(EQUITY_INFO)
        result = get_symbol_info("AAPL")
        assert result is not None
        assert result.symbol == "AAPL"

    @patch("app.utils.conv.to_yf_symbol_format", return_value="SPY")
    @patch("app.services.stock.yf.Ticker")
    def test_returns_symbol_info_for_etf(self, mock_ticker_cls, mock_to_yf):
        mock_ticker_cls.return_value = _make_ticker_mock(ETF_INFO)
        result = get_symbol_info("SPY")
        assert result is not None

    @patch("app.utils.conv.to_yf_symbol_format", return_value="VTSAX")
    @patch("app.services.stock.yf.Ticker")
    def test_returns_symbol_info_for_mutual_fund(self, mock_ticker_cls, mock_to_yf):
        mock_ticker_cls.return_value = _make_ticker_mock(MUTUAL_FUND_INFO)

        result = get_symbol_info("VTSAX")

        assert result is not None
        assert result.symbol == "VTSAX"

    @patch("app.utils.conv.to_yf_symbol_format", return_value="VTSAX")
    @patch("app.services.stock.yf.Ticker")
    def test_returns_none_for_unsupported_quote_type(self, mock_ticker_cls, mock_to_yf):
        mock_ticker_cls.return_value = _make_ticker_mock(UNSUPPORTED_INFO)
        result = get_symbol_info("VTSAX")
        assert result is None

    @patch("app.utils.conv.to_yf_symbol_format", return_value="FAKE")
    @patch("app.services.stock.yf.Ticker")
    def test_returns_none_when_quote_type_is_none(self, mock_ticker_cls, mock_to_yf):
        mock_ticker_cls.return_value = _make_ticker_mock(NONE_QUOTE_TYPE_INFO)
        result = get_symbol_info("FAKE")
        assert result is None

    @patch("app.services.stock.yf.Ticker")
    def test_accepts_exchange_qualified_symbols(self, mock_ticker_cls):
        info = {
            **EQUITY_INFO,
            "symbol": "CBA.AX",
            "fullExchangeName": "ASX",
            "country": "Australia",
        }
        ticker = _make_ticker_mock(info)
        mock_ticker_cls.side_effect = {"CBA.AX": ticker}.__getitem__

        result = get_symbol_info("ASX:CBA")

        assert result is not None
        assert result.normalized_symbol == "ASX:CBA"

    @patch("app.services.stock.yf.Ticker")
    def test_model_validation_failures_propagate(self, mock_ticker_cls):
        invalid_info = {
            **EQUITY_INFO,
            "regularMarketPrice": "not-a-number",
        }
        mock_ticker_cls.return_value = _make_ticker_mock(invalid_info)

        with pytest.raises(pydantic.ValidationError):
            get_symbol_info("AAPL")


# ---------------------------------------------------------------------------
# get_symbol_overview
# ---------------------------------------------------------------------------


class TestGetSymbolOverview:
    @patch("app.utils.conv.to_yf_symbol_format", return_value="AAPL")
    @patch("app.services.stock.yf.Ticker")
    def test_returns_overview_for_equity(self, mock_ticker_cls, mock_to_yf):
        mock_ticker_cls.return_value = _make_ticker_mock(EQUITY_INFO)
        result = get_symbol_overview("AAPL")
        assert result is not None

    @patch("app.utils.conv.to_yf_symbol_format", return_value="AAPL")
    @patch("app.services.stock.yf.Ticker")
    def test_sets_normalized_symbol_for_overview(self, mock_ticker_cls, mock_to_yf):
        mock_ticker_cls.return_value = _make_ticker_mock(EQUITY_INFO)

        result = get_symbol_overview("AAPL")

        assert result is not None
        assert result.normalized_symbol == "NASDAQ:AAPL"

    @pytest.mark.parametrize(
        ("info", "expected_quote_type"),
        [
            (ETF_INFO, "ETF"),
            (MUTUAL_FUND_INFO, "MUTUALFUND"),
        ],
    )
    @patch("app.services.stock.yf.Ticker")
    def test_returns_overview_for_supported_fund_types(
        self,
        mock_ticker_cls,
        info,
        expected_quote_type,
    ):
        mock_ticker_cls.return_value = _make_ticker_mock(info)

        result = get_symbol_overview(info["symbol"])

        assert result is not None
        assert result.quote_type == expected_quote_type

    @patch("app.utils.conv.to_yf_symbol_format", return_value="VTSAX")
    @patch("app.services.stock.yf.Ticker")
    def test_returns_none_for_unsupported_quote_type(self, mock_ticker_cls, mock_to_yf):
        mock_ticker_cls.return_value = _make_ticker_mock(UNSUPPORTED_INFO)
        result = get_symbol_overview("VTSAX")
        assert result is None

    @patch("app.services.stock.yf.Ticker")
    def test_returns_none_when_quote_type_is_missing(self, mock_ticker_cls):
        mock_ticker_cls.return_value = _make_ticker_mock(NONE_QUOTE_TYPE_INFO)

        result = get_symbol_overview("FAKE")

        assert result is None

    @patch("app.services.stock.yf.Ticker")
    def test_accepts_exchange_qualified_symbols(self, mock_ticker_cls):
        info = {
            **EQUITY_INFO,
            "symbol": "CBA.AX",
            "fullExchangeName": "ASX",
            "country": "Australia",
        }
        ticker = _make_ticker_mock(info)
        mock_ticker_cls.side_effect = {"CBA.AX": ticker}.__getitem__

        result = get_symbol_overview("ASX:CBA")

        assert result is not None
        assert result.normalized_symbol == "ASX:CBA"

    @patch("app.services.stock.yf.Ticker")
    def test_model_validation_failures_propagate(self, mock_ticker_cls):
        invalid_info = {
            **EQUITY_INFO,
            "symbol": None,
        }
        mock_ticker_cls.return_value = _make_ticker_mock(invalid_info)

        with pytest.raises(pydantic.ValidationError):
            get_symbol_overview("AAPL")


# ---------------------------------------------------------------------------
# get_stock_quotes
# ---------------------------------------------------------------------------


class TestGetStockQuotes:
    @patch("app.utils.conv.to_yf_symbol_format", side_effect=lambda s: s)
    @patch("app.services.stock.yf.Tickers")
    def test_returns_quotes_for_valid_symbols(self, mock_tickers_cls, mock_to_yf):
        ticker1 = _make_ticker_mock(EQUITY_INFO)
        ticker2 = _make_ticker_mock(ETF_INFO)
        mock_tickers_instance = MagicMock()
        mock_tickers_instance.tickers = {"AAPL": ticker1, "SPY": ticker2}
        mock_tickers_cls.return_value = mock_tickers_instance

        result = get_stock_quotes(["AAPL", "SPY"])
        assert "AAPL" in result
        assert "SPY" in result
        assert result["AAPL"].market_price == 195.0
        assert result["SPY"].market_price == 450.0

    @patch("app.utils.conv.to_yf_symbol_format", side_effect=lambda s: s)
    @patch("app.services.stock.yf.Tickers")
    def test_excludes_unsupported_quote_types(self, mock_tickers_cls, mock_to_yf):
        ticker1 = _make_ticker_mock(EQUITY_INFO)
        ticker2 = _make_ticker_mock(UNSUPPORTED_INFO)
        mock_tickers_instance = MagicMock()
        mock_tickers_instance.tickers = {"AAPL": ticker1, "VTSAX": ticker2}
        mock_tickers_cls.return_value = mock_tickers_instance

        result = get_stock_quotes(["AAPL", "VTSAX"])
        assert "AAPL" in result
        assert "VTSAX" not in result

    @patch("app.utils.conv.to_yf_symbol_format", side_effect=lambda s: s)
    @patch("app.services.stock.yf.Tickers")
    def test_includes_mutual_fund_quotes(self, mock_tickers_cls, mock_to_yf):
        ticker1 = _make_ticker_mock(MUTUAL_FUND_INFO)
        mock_tickers_instance = MagicMock()
        mock_tickers_instance.tickers = {"VTSAX": ticker1}
        mock_tickers_cls.return_value = mock_tickers_instance

        result = get_stock_quotes(["VTSAX"])

        assert "VTSAX" in result
        assert result["VTSAX"].market_price == 450.0

    @patch("app.services.stock.yf.Tickers")
    def test_accepts_exchange_qualified_symbols(self, mock_tickers_cls):
        info = {
            **EQUITY_INFO,
            "symbol": "CBA.AX",
            "fullExchangeName": "ASX",
            "country": "Australia",
        }
        tickers = MagicMock()
        tickers.tickers = {"CBA.AX": _make_ticker_mock(info)}
        mock_tickers_cls.side_effect = {"CBA.AX": tickers}.__getitem__

        result = get_stock_quotes(["ASX:CBA"])

        assert list(result) == ["ASX:CBA"]
        assert result["ASX:CBA"].market_price == 195.0

    @patch("app.utils.conv.to_yf_symbol_format", side_effect=lambda s: s)
    @patch("app.services.stock.yf.Tickers")
    def test_handles_symbol_not_in_tickers(self, mock_tickers_cls, mock_to_yf):
        mock_tickers_instance = MagicMock()
        mock_tickers_instance.tickers = {}
        mock_tickers_cls.return_value = mock_tickers_instance

        result = get_stock_quotes(["NONEXIST"])
        assert result == {}

    @patch("app.utils.conv.to_yf_symbol_format", side_effect=lambda s: s)
    @patch("app.services.stock.yf.Tickers")
    def test_empty_symbols_list(self, mock_tickers_cls, mock_to_yf):
        mock_tickers_instance = MagicMock()
        mock_tickers_instance.tickers = {}
        mock_tickers_cls.return_value = mock_tickers_instance

        result = get_stock_quotes([])
        assert result == {}

    @patch("app.services.stock.yf.Tickers")
    def test_omits_symbols_with_missing_quote_type(self, mock_tickers_cls):
        tickers = MagicMock()
        tickers.tickers = {"FAKE": _make_ticker_mock(NONE_QUOTE_TYPE_INFO)}
        mock_tickers_cls.return_value = tickers

        result = get_stock_quotes(["FAKE"])

        assert result == {}

    @patch("app.services.stock.yf.Tickers", side_effect=RuntimeError("provider unavailable"))
    def test_provider_failures_propagate(self, mock_tickers_cls):
        with pytest.raises(RuntimeError):
            get_stock_quotes(["AAPL"])

    @patch("app.services.stock.yf.Tickers")
    def test_metadata_failures_propagate(self, mock_tickers_cls):
        class FailingTicker:
            @property
            def info(self):
                raise RuntimeError("metadata unavailable")

        tickers = MagicMock()
        tickers.tickers = {"AAPL": FailingTicker()}
        mock_tickers_cls.return_value = tickers

        with pytest.raises(RuntimeError, match="metadata unavailable"):
            get_stock_quotes(["AAPL"])

    @patch("app.services.stock.yf.Tickers")
    def test_model_validation_failures_propagate(self, mock_tickers_cls):
        invalid_info = {
            **EQUITY_INFO,
            "regularMarketPrice": "not-a-number",
        }
        tickers = MagicMock()
        tickers.tickers = {"AAPL": _make_ticker_mock(invalid_info)}
        mock_tickers_cls.return_value = tickers

        with pytest.raises(pydantic.ValidationError):
            get_stock_quotes(["AAPL"])


# ---------------------------------------------------------------------------
# get_stock_quote_at_date
# ---------------------------------------------------------------------------


class TestGetStockQuoteAtDate:
    @patch("app.utils.conv.to_yf_symbol_format", return_value="AAPL")
    @patch("app.services.stock.yf.Ticker")
    def test_returns_latest_quote_no_later_than_the_requested_date(self, mock_ticker_cls, mock_to_yf):
        hist_df = _make_history_df(5)
        ticker = _make_ticker_mock(EQUITY_INFO, hist_df)
        mock_ticker_cls.return_value = ticker

        result = get_stock_quote_at_date("AAPL", "2026-01-03")

        assert result is not None
        assert result.close == hist_df.iloc[2]["Close"]
        assert result.volume == int(hist_df.iloc[2]["Volume"])

    @patch("app.utils.conv.to_yf_symbol_format", return_value="AAPL")
    @patch("app.services.stock.yf.Ticker")
    def test_uses_the_previous_trading_day_for_a_weekend(self, mock_ticker_cls, mock_to_yf):
        hist_df = _make_history_df(5).loc[["2026-01-02", "2026-01-05"]]
        ticker = _make_ticker_mock(EQUITY_INFO, hist_df)
        mock_ticker_cls.return_value = ticker

        result = get_stock_quote_at_date("AAPL", "2026-01-04")

        assert result is not None
        assert result.close == hist_df.iloc[0]["Close"]

    @pytest.mark.parametrize("info", [ETF_INFO, MUTUAL_FUND_INFO])
    @patch("app.services.stock.yf.Ticker")
    def test_returns_quotes_for_supported_fund_types(self, mock_ticker_cls, info):
        hist_df = _make_history_df(2)
        mock_ticker_cls.return_value = _make_ticker_mock(info, hist_df)

        result = get_stock_quote_at_date(info["symbol"], "2026-01-02")

        assert result is not None
        assert result.close == hist_df.iloc[-1]["Close"]

    @patch("app.utils.conv.to_yf_symbol_format", return_value="AAPL")
    @patch("app.services.stock.yf.Ticker")
    def test_returns_none_for_invalid_date_format(self, mock_ticker_cls, mock_to_yf):
        mock_ticker_cls.return_value = _make_ticker_mock(EQUITY_INFO)
        result = get_stock_quote_at_date("AAPL", "not-a-date")
        assert result is None

    @patch("app.utils.conv.to_yf_symbol_format", return_value="AAPL")
    @patch("app.services.stock.yf.Ticker")
    def test_returns_none_for_unsupported_quote_type(self, mock_ticker_cls, mock_to_yf):
        mock_ticker_cls.return_value = _make_ticker_mock(UNSUPPORTED_INFO)
        result = get_stock_quote_at_date("AAPL", "2026-01-01")
        assert result is None

    @patch("app.services.stock.yf.Ticker")
    def test_returns_none_when_quote_type_is_missing(self, mock_ticker_cls):
        mock_ticker_cls.return_value = _make_ticker_mock(NONE_QUOTE_TYPE_INFO)

        result = get_stock_quote_at_date("FAKE", "2026-01-01")

        assert result is None

    @patch("app.utils.conv.to_yf_symbol_format", return_value="AAPL")
    @patch("app.services.stock.yf.Ticker")
    def test_returns_none_when_history_empty(self, mock_ticker_cls, mock_to_yf):
        empty_df = pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume", "Dividends"])
        mock_ticker_cls.return_value = _make_ticker_mock(EQUITY_INFO, empty_df)

        result = get_stock_quote_at_date("AAPL", "2026-01-01")

        assert result is None

    @patch("app.utils.conv.to_yf_symbol_format", return_value="AAPL")
    @patch("app.services.stock.yf.Ticker")
    def test_returns_none_when_only_history_older_than_the_lookback_is_available(
        self,
        mock_ticker_cls,
        mock_to_yf,
    ):
        old_history = _make_history_df(1)
        ticker = _make_ticker_mock(EQUITY_INFO, old_history)
        mock_ticker_cls.return_value = ticker

        result = get_stock_quote_at_date("AAPL", "2026-02-01")

        assert result is None

    @patch("app.services.stock.yf.Ticker")
    def test_accepts_exchange_qualified_symbols(self, mock_ticker_cls):
        info = {
            **EQUITY_INFO,
            "symbol": "CBA.AX",
            "fullExchangeName": "ASX",
            "country": "Australia",
        }
        history = _make_history_df(1)
        ticker = _make_ticker_mock(info, history)
        mock_ticker_cls.side_effect = {"CBA.AX": ticker}.__getitem__

        result = get_stock_quote_at_date("ASX:CBA", "2026-01-01")

        assert result is not None
        assert result.close == history.iloc[0]["Close"]

    @patch("app.services.stock.yf.Ticker")
    def test_model_validation_failures_propagate(self, mock_ticker_cls):
        invalid_history = _make_history_df(1)
        invalid_history["Open"] = ["not-a-number"]
        mock_ticker_cls.return_value = _make_ticker_mock(EQUITY_INFO, invalid_history)

        with pytest.raises(pydantic.ValidationError):
            get_stock_quote_at_date("AAPL", "2026-01-01")


# ---------------------------------------------------------------------------
# get_symbol_history
# ---------------------------------------------------------------------------


class TestGetSymbolHistory:
    @patch("app.utils.conv.to_yf_symbol_format", return_value="AAPL")
    @patch("app.services.stock.yf.Ticker")
    def test_returns_history_points_for_equity(self, mock_ticker_cls, mock_to_yf):
        hist_df = _make_history_df(3)
        ticker = _make_ticker_mock(EQUITY_INFO, hist_df)
        mock_ticker_cls.return_value = ticker

        result = get_symbol_history("AAPL", 3)
        assert result is not None
        assert len(result) == 3
        assert result[0].open == hist_df.iloc[0]["Open"]
        assert result[0].close == hist_df.iloc[0]["Close"]
        assert result[0].volume == int(hist_df.iloc[0]["Volume"])
        assert result[0].timestamp == int(hist_df.index[0].timestamp())

    @pytest.mark.parametrize("info", [ETF_INFO, MUTUAL_FUND_INFO])
    @patch("app.services.stock.yf.Ticker")
    def test_returns_history_for_supported_fund_types(self, mock_ticker_cls, info):
        hist_df = _make_history_df(2)
        mock_ticker_cls.return_value = _make_ticker_mock(info, hist_df)

        result = get_symbol_history(info["symbol"], 2)

        assert result is not None
        assert [point.close for point in result] == list(hist_df["Close"])

    @patch("app.utils.conv.to_yf_symbol_format", return_value="AAPL")
    @patch("app.services.stock.yf.Ticker")
    def test_requests_given_number_of_days(self, mock_ticker_cls, mock_to_yf):
        ticker = _make_ticker_mock(EQUITY_INFO, _make_history_df(3))
        mock_ticker_cls.return_value = ticker

        get_symbol_history("AAPL", 30)
        _, kwargs = ticker.history.call_args
        assert kwargs["period"] == "30d"

    @patch("app.utils.conv.to_yf_symbol_format", return_value="AAPL")
    @patch("app.services.stock.yf.Ticker")
    def test_defaults_to_100_days_when_non_positive(self, mock_ticker_cls, mock_to_yf):
        ticker = _make_ticker_mock(EQUITY_INFO, _make_history_df(3))
        mock_ticker_cls.return_value = ticker

        get_symbol_history("AAPL", 0)
        _, kwargs = ticker.history.call_args
        assert kwargs["period"] == "100d"

    @patch("app.utils.conv.to_yf_symbol_format", return_value="AAPL")
    @patch("app.services.stock.yf.Ticker")
    def test_returns_none_for_unsupported_quote_type(self, mock_ticker_cls, mock_to_yf):
        mock_ticker_cls.return_value = _make_ticker_mock(UNSUPPORTED_INFO)
        result = get_symbol_history("AAPL", 30)
        assert result is None

    @patch("app.utils.conv.to_yf_symbol_format", return_value="AAPL")
    @patch("app.services.stock.yf.Ticker")
    def test_returns_none_when_quote_type_is_none(self, mock_ticker_cls, mock_to_yf):
        mock_ticker_cls.return_value = _make_ticker_mock(NONE_QUOTE_TYPE_INFO)
        result = get_symbol_history("AAPL", 30)
        assert result is None

    @patch("app.utils.conv.to_yf_symbol_format", return_value="AAPL")
    @patch("app.services.stock.yf.Ticker")
    def test_returns_empty_list_when_history_empty(self, mock_ticker_cls, mock_to_yf):
        empty_df = pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume", "Dividends"])
        ticker = _make_ticker_mock(EQUITY_INFO, empty_df)
        mock_ticker_cls.return_value = ticker

        result = get_symbol_history("AAPL", 30)
        assert result == []

    @patch("app.services.stock.yf.Ticker")
    def test_accepts_exchange_qualified_symbols(self, mock_ticker_cls):
        info = {
            **EQUITY_INFO,
            "symbol": "CBA.AX",
            "fullExchangeName": "ASX",
            "country": "Australia",
        }
        history = _make_history_df(2)
        ticker = _make_ticker_mock(info, history)
        mock_ticker_cls.side_effect = {"CBA.AX": ticker}.__getitem__

        result = get_symbol_history("ASX:CBA", 2)

        assert result is not None
        assert [point.close for point in result] == list(history["Close"])

    @patch("app.services.stock.yf.Ticker")
    def test_model_validation_failures_propagate(self, mock_ticker_cls):
        invalid_history = _make_history_df(1)
        invalid_history["Open"] = ["not-a-number"]
        mock_ticker_cls.return_value = _make_ticker_mock(EQUITY_INFO, invalid_history)

        with pytest.raises(pydantic.ValidationError):
            get_symbol_history("AAPL", 1)
