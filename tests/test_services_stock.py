from unittest.mock import MagicMock, patch

import pandas as pd

from app.services.stock import (
    get_stock_quote_at_date,
    get_stock_quotes,
    get_symbol_info,
    get_symbol_overview,
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
    "quoteType": "MUTUALFUND",
    "symbol": "VTSAX",
    "currency": "USD",
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
        mock_to_yf.assert_called_once_with("AAPL")

    @patch("app.utils.conv.to_yf_symbol_format", return_value="SPY")
    @patch("app.services.stock.yf.Ticker")
    def test_returns_symbol_info_for_etf(self, mock_ticker_cls, mock_to_yf):
        mock_ticker_cls.return_value = _make_ticker_mock(ETF_INFO)
        result = get_symbol_info("SPY")
        assert result is not None

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

    @patch("app.utils.conv.to_yf_symbol_format", return_value="CBA.AX")
    @patch("app.services.stock.yf.Ticker")
    def test_converts_exchange_code_format(self, mock_ticker_cls, mock_to_yf):
        mock_ticker_cls.return_value = _make_ticker_mock(EQUITY_INFO)
        get_symbol_info("ASX:CBA")
        mock_to_yf.assert_called_once_with("ASX:CBA")


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

    @patch("app.utils.conv.to_yf_symbol_format", return_value="VTSAX")
    @patch("app.services.stock.yf.Ticker")
    def test_returns_none_for_unsupported_quote_type(self, mock_ticker_cls, mock_to_yf):
        mock_ticker_cls.return_value = _make_ticker_mock(UNSUPPORTED_INFO)
        result = get_symbol_overview("VTSAX")
        assert result is None


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


# ---------------------------------------------------------------------------
# get_stock_quote_at_date
# ---------------------------------------------------------------------------


class TestGetStockQuoteAtDate:
    @patch("app.utils.conv.to_yf_symbol_format", return_value="AAPL")
    @patch("app.services.stock.yf.Ticker")
    def test_returns_history_point_for_valid_date(self, mock_ticker_cls, mock_to_yf):
        hist_df = _make_history_df(5)
        ticker = _make_ticker_mock(EQUITY_INFO, hist_df)
        mock_ticker_cls.return_value = ticker

        result = get_stock_quote_at_date("AAPL", "2026-01-03")
        assert result is not None
        assert result.close == hist_df.iloc[-1]["Close"]
        assert result.volume == int(hist_df.iloc[-1]["Volume"])

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

    @patch("app.utils.conv.to_yf_symbol_format", return_value="AAPL")
    @patch("app.services.stock.yf.Ticker")
    def test_returns_none_when_history_empty(self, mock_ticker_cls, mock_to_yf):
        empty_df = pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume", "Dividends"])
        ticker = _make_ticker_mock(EQUITY_INFO, empty_df)
        mock_ticker_cls.return_value = ticker

        result = get_stock_quote_at_date("AAPL", "2026-01-01")
        assert result is None
