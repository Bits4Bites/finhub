import datetime
import zoneinfo

import pandas
import pydantic
import pytest

from app.models import stocks as models_stocks


class _FakeTicker:
    def __init__(self, **info_overrides):
        ex_dividend_at = datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)
        last_dividend_at = datetime.datetime(2025, 12, 1, tzinfo=datetime.UTC)
        self.info = {
            "symbol": " cba.ax ",
            "currency": " aud ",
            "fullExchangeName": "ASX",
            "country": "Australia",
            "shortName": "CBA",
            "longName": "Commonwealth Bank of Australia",
            "sector": "Financial Services",
            "industry": "Banks - Diversified",
            "website": "https://www.commbank.com.au",
            "longBusinessSummary": "Provides banking and financial services.",
            "quoteType": "EQUITY",
            "totalCash": 10_000,
            "totalCashPerShare": 10.0,
            "totalDebt": 5_000,
            "totalDebtPerShare": 5.0,
            "totalRevenue": 50_000,
            "totalRevenuePerShare": 50.0,
            "ebitda": 8_000,
            "ebitdaMargins": 0.16,
            "earningsGrowth": 0.10,
            "revenueGrowth": 0.08,
            "grossMargins": 0.50,
            "operatingMargins": 0.20,
            "profitMargins": 0.15,
            "marketCap": None,
            "regularMarketPrice": 150.0,
            "trailingEps": 5.0,
            "dividendRate": 4.5,
            "dividendYield": 0.03,
            "exDividendDate": int(ex_dividend_at.timestamp()),
            "fiveYearAvgDividendYield": 3.5,
            "trailingAnnualDividendRate": 4.2,
            "trailingAnnualDividendYield": 0.028,
            "lastDividendValue": 2.25,
            "lastDividendDate": int(last_dividend_at.timestamp()),
        }
        self.info.update(info_overrides)
        index = pandas.date_range(
            "2025-03-03",
            periods=220,
            freq="B",
            tz="Australia/Sydney",
        )
        closes = pandas.Series(
            [100.0 + index_value / 10 for index_value in range(len(index))],
            index=index,
        )
        dividends = pandas.Series(0.0, index=index)
        dividends.iloc[-100] = 2.0
        dividends.iloc[-20] = 2.25
        self._history = pandas.DataFrame(
            {
                "Open": closes - 0.5,
                "High": closes + 1.0,
                "Low": closes - 1.0,
                "Close": closes,
                "Volume": [1_000 + index_value for index_value in range(len(index))],
                "Dividends": dividends,
            },
            index=index,
        )

    def history(self, **kwargs):
        return self._history.copy()


def test_symbol_base_constructor_normalizes_market_identity():
    symbol = models_stocks.SymbolBase(_FakeTicker())

    assert symbol.model_dump(mode="json") == {
        "symbol": "CBA.AX",
        "normalized_symbol": "ASX:CBA",
        "currency": "AUD",
        "exchange": "ASX",
        "country": "AU",
    }


@pytest.mark.parametrize(
    "info_overrides",
    [
        {"currency": "A$D"},
        {"country": "Atlantis"},
    ],
)
def test_symbol_base_constructor_rejects_invalid_documented_identifier(info_overrides):
    with pytest.raises(pydantic.ValidationError):
        models_stocks.SymbolBase(_FakeTicker(**info_overrides))


def test_symbol_overview_constructor_extracts_company_metadata():
    overview = models_stocks.SymbolOverview(_FakeTicker())

    assert overview.model_dump(mode="json") == {
        "symbol": "CBA.AX",
        "normalized_symbol": "ASX:CBA",
        "currency": "AUD",
        "exchange": "ASX",
        "country": "AU",
        "short_name": "CBA",
        "long_name": "Commonwealth Bank of Australia",
        "sector": "Financial Services",
        "industry": "Banks - Diversified",
        "website": "https://www.commbank.com.au",
        "description": "Provides banking and financial services.",
        "quote_type": "EQUITY",
        "asset_type": "STANDARD",
        "total_cash": 10_000,
        "total_cash_per_share": 10.0,
        "total_debt": 5_000,
        "total_debt_per_share": 5.0,
        "total_revenue": 50_000,
        "total_revenue_per_share": 50.0,
        "ebitda": 8_000,
        "ebitda_margins": 0.16,
        "earnings_growth": 0.10,
        "revenue_growth": 0.08,
        "gross_margins": 0.50,
        "operating_margins": 0.20,
        "profit_margins": 0.15,
        "market_cap": None,
        "cap_size": None,
        "market_index": None,
    }


def test_symbol_dividend_constructor_uses_exchange_local_timestamps_and_trailing_year():
    ticker = _FakeTicker()

    dividend = models_stocks.SymbolDividend(ticker)

    exchange_timezone = zoneinfo.ZoneInfo("Australia/Sydney")
    expected_ex_date = datetime.datetime.fromtimestamp(
        ticker.info["exDividendDate"],
        tz=exchange_timezone,
    ).isoformat(sep=" ", timespec="seconds")
    expected_last_date = datetime.datetime.fromtimestamp(
        ticker.info["lastDividendDate"],
        tz=exchange_timezone,
    ).isoformat(sep=" ", timespec="seconds")
    assert dividend.model_dump(mode="json") == {
        "dividend_rate": 4.5,
        "dividend_yield": 0.03,
        "payout_frequency": 2,
        "ex_dividend_date": ticker.info["exDividendDate"],
        "ex_dividend_date_str": expected_ex_date,
        "five_year_avg_dividend_yield": 3.5,
        "trailing_annual_dividend_rate": 4.2,
        "trailing_annual_dividend_yield": 0.028,
        "last_dividend_value": 2.25,
        "last_dividend_date": ticker.info["lastDividendDate"],
        "last_dividend_date_str": expected_last_date,
    }


def test_stock_history_constructor_uses_latest_trading_observations():
    ticker = _FakeTicker()

    history = models_stocks.StockHistory(ticker)

    latest_30 = ticker._history.iloc[-30:]
    assert history.recent_high_price == pytest.approx(latest_30["Close"].max())
    assert history.pull_pack_percent == 0
    assert history.current_volume == ticker._history["Volume"].iloc[-1]
    assert history.yesterday_volume == ticker._history["Volume"].iloc[-2]
    assert history.average_volume_30d == int(latest_30["Volume"].mean())
    assert history.ma10 == pytest.approx(121.45)
    assert history.ma20 == pytest.approx(120.95)
    assert history.ma50 == pytest.approx(119.45)
    assert history.ma100 == pytest.approx(116.95)
    assert history.ma200 == pytest.approx(111.95)
    assert history.rsi14 == pytest.approx(100.0)
    assert len(history.history_90d) == 90
    for point, source_index, source_row in (
        (history.history_90d[0], ticker._history.index[-90], ticker._history.iloc[-90]),
        (history.history_90d[-1], ticker._history.index[-1], ticker._history.iloc[-1]),
    ):
        assert point.timestamp == int(source_index.timestamp())
        assert point.timestamp_str == source_index.isoformat(sep=" ", timespec="seconds")
        assert datetime.datetime.fromisoformat(point.timestamp_str).utcoffset() is not None
        assert point.currency == "AUD"
        assert point.open == pytest.approx(source_row["Open"])
        assert point.high == pytest.approx(source_row["High"])
        assert point.low == pytest.approx(source_row["Low"])
        assert point.close == pytest.approx(source_row["Close"])
        assert point.volume == source_row["Volume"]
        assert point.dividends == pytest.approx(source_row["Dividends"])
        assert point.rsi14 == pytest.approx(100.0)
        assert point.dvt is not None and point.dvt > 0


def test_symbol_info_constructor_combines_overview_quote_dividend_and_history():
    info = models_stocks.SymbolInfo(_FakeTicker())

    serialized = info.model_dump(mode="json")
    assert serialized["normalized_symbol"] == "ASX:CBA"
    assert serialized["stock_quote"]["trailing_eps"] == 5.0
    assert serialized["dividend"]["payout_frequency"] == 2
    assert len(serialized["stock_history"]["history_90d"]) == 90
