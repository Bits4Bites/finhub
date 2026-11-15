import asyncio
import math
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from app.services import event, events_div


def _dividend_frame(rows):
    columns = [
        "Ticker",
        "Company",
        "Ex-Div Date",
        "Payment Date",
        "Div Amount",
        "Div Yield",
        "Market Cap",
        "Exchange",
        "Currency",
    ]
    return pd.DataFrame(rows, columns=columns)


class TestEarningsEvents:
    @pytest.mark.parametrize(
        ("public_function", "crawler_target", "invalid_index"),
        [
            (
                event.get_asx_upcoming_earnings_events,
                "app.services.event.services_crawler_earnings.scrape_earnings_asx",
                "SP500",
            ),
            (
                event.get_us_upcoming_earnings_events,
                "app.services.event.services_crawler_earnings.scrape_earnings_us",
                "ASX200",
            ),
        ],
    )
    def test_invalid_index_returns_empty_without_crawling(self, public_function, crawler_target, invalid_index):
        with patch(crawler_target, new_callable=AsyncMock) as crawler:
            result = asyncio.run(public_function(invalid_index))

        assert result == []
        crawler.assert_not_awaited()

    def test_asx_events_normalize_symbol_date_defaults_and_link(self):
        raw_data = pd.DataFrame(
            {
                "Symbol": ["CBA"],
                "Company Name": ["Commonwealth Bank"],
                "Announcement Date": ["2026-11-20"],
                "Url": ["https://source.example/ignored"],
            }
        )

        with patch(
            "app.services.event.services_crawler_earnings.scrape_earnings_asx",
            new_callable=AsyncMock,
            return_value=raw_data,
        ):
            result = asyncio.run(event.get_asx_upcoming_earnings_events())

        assert len(result) == 1
        earnings = result[0]
        assert earnings.symbol == "ASX:CBA"
        assert earnings.exchange == "ASX"
        assert earnings.company_name == "Commonwealth Bank"
        assert earnings.timestamp_str.startswith("2026-11-20 00:00:00")
        assert earnings.timestamp > 0
        assert earnings.event_category == "earnings"
        assert earnings.source_name == "TipRanks"
        assert earnings.status == "estimated"
        assert earnings.report_period == "N/A"
        assert earnings.link == "https://www.tipranks.com/stocks/au:cba/earnings"

    def test_asx_index_filter_is_case_insensitive(self):
        raw_data = pd.DataFrame(
            {
                "Symbol": ["CBA"],
                "Company Name": ["Commonwealth Bank"],
                "Announcement Date": ["2026-11-20"],
            }
        )

        with patch(
            "app.services.event.services_crawler_earnings.scrape_earnings_asx",
            new_callable=AsyncMock,
            return_value=raw_data,
        ):
            result = asyncio.run(event.get_asx_upcoming_earnings_events("asx20"))

        assert [earnings.symbol for earnings in result] == ["ASX:CBA"]

    def test_us_events_keep_only_major_exchanges(self):
        raw_data = pd.DataFrame(
            {
                "Symbol": ["AAPL", "PINK1"],
                "Exchange Name": ["NASDAQ", "PINK"],
                "Company Name": ["Apple Inc.", "Pink Sheets Co"],
                "Announcement Date": ["2026-11-20", "2026-11-20"],
            }
        )

        with patch(
            "app.services.event.services_crawler_earnings.scrape_earnings_us",
            new_callable=AsyncMock,
            return_value=raw_data,
        ):
            result = asyncio.run(event.get_us_upcoming_earnings_events())

        assert [earnings.symbol for earnings in result] == ["NASDAQ:AAPL"]
        assert result[0].company_name == "Apple Inc."
        assert result[0].link == "https://www.tipranks.com/stocks/aapl/earnings"
        assert result[0].timestamp_str.endswith("-05:00")

    def test_empty_crawler_frame_returns_no_events(self):
        with patch(
            "app.services.event.services_crawler_earnings.scrape_earnings_asx",
            new_callable=AsyncMock,
            return_value=pd.DataFrame(),
        ):
            assert asyncio.run(event.get_asx_upcoming_earnings_events()) == []

    def test_missing_required_crawler_column_is_rejected(self):
        raw_data = pd.DataFrame({"Symbol": ["CBA"], "Company Name": ["Commonwealth Bank"]})

        with (
            patch(
                "app.services.event.services_crawler_earnings.scrape_earnings_asx",
                new_callable=AsyncMock,
                return_value=raw_data,
            ),
            pytest.raises(ValueError, match="Announcement Date"),
        ):
            asyncio.run(event.get_asx_upcoming_earnings_events())


class TestDividendEvents:
    @pytest.mark.parametrize(
        ("public_function", "crawler_target", "invalid_index"),
        [
            (
                events_div.get_asx_upcoming_dividends_events,
                "app.services.events_div.services_crawler_div.scrape_dividends_asx",
                "SP500",
            ),
            (
                events_div.get_us_upcoming_dividends_events,
                "app.services.events_div.services_crawler_div.scrape_dividends_us",
                "ASX200",
            ),
            (
                events_div.get_vn_upcoming_dividends_events,
                "app.services.events_div.services_crawler_div.scrape_dividends_vn",
                "NASDAQ100",
            ),
        ],
    )
    def test_invalid_index_returns_empty_without_crawling(self, public_function, crawler_target, invalid_index):
        with patch(crawler_target, new_callable=AsyncMock) as crawler:
            result = asyncio.run(public_function(invalid_index))

        assert result == []
        crawler.assert_not_awaited()

    def test_asx_events_normalize_values_and_classify_distributions(self):
        raw_data = _dividend_frame(
            [
                {
                    "Ticker": "VAS",
                    "Company": "Vanguard Australian Shares ETF",
                    "Ex-Div Date": "2026-11-20",
                    "Payment Date": "2026-12-15",
                    "Div Amount": 1.5,
                    "Div Yield": 0.03,
                    "Market Cap": 20_000_000_000,
                    "Exchange": "ASX",
                    "Currency": "AUD",
                }
            ]
        )

        with patch(
            "app.services.events_div.services_crawler_div.scrape_dividends_asx",
            new_callable=AsyncMock,
            return_value=raw_data,
        ):
            result = asyncio.run(events_div.get_asx_upcoming_dividends_events())

        assert len(result) == 1
        dividend = result[0]
        assert dividend.symbol == "ASX:VAS"
        assert dividend.company_name == "Vanguard Australian Shares ETF"
        assert dividend.timestamp_str.startswith("2026-11-20 00:00:00")
        assert dividend.payment_date.startswith("2026-12-15 00:00:00")
        assert dividend.amount == 1.5
        assert dividend.dividend_yield == 0.03
        assert dividend.currency == "AUD"
        assert dividend.event_category == "distribution"
        assert dividend.source_name == "ASX"
        assert dividend.status == "declared"
        assert dividend.link == "https://www.asx.com.au/markets/company/VAS"

    def test_us_events_drop_unknown_exchanges(self):
        raw_data = _dividend_frame(
            [
                {
                    "Ticker": "AAPL",
                    "Company": "Apple Inc.",
                    "Ex-Div Date": "2026-11-20",
                    "Payment Date": None,
                    "Div Amount": 0.25,
                    "Div Yield": 0.005,
                    "Market Cap": 3_000_000_000_000,
                    "Exchange": "NASDAQ",
                    "Currency": "USD",
                },
                {
                    "Ticker": "UNKNOWN",
                    "Company": "Unknown Co",
                    "Ex-Div Date": "2026-11-20",
                    "Payment Date": None,
                    "Div Amount": 1.0,
                    "Div Yield": 0.01,
                    "Market Cap": None,
                    "Exchange": "N/A",
                    "Currency": "USD",
                },
            ]
        )

        with patch(
            "app.services.events_div.services_crawler_div.scrape_dividends_us",
            new_callable=AsyncMock,
            return_value=raw_data,
        ):
            result = asyncio.run(events_div.get_us_upcoming_dividends_events())

        assert [dividend.symbol for dividend in result] == ["NASDAQ:AAPL"]
        assert result[0].payment_date is None
        assert result[0].event_category == "dividend"
        assert result[0].link == "https://stockanalysis.com/stocks/aapl/dividend/"

    def test_vn_events_are_cash_dividends_not_distributions(self):
        raw_data = _dividend_frame(
            [
                {
                    "Ticker": "VNM",
                    "Company": "VNM PROPERTY FUND",
                    "Ex-Div Date": "2026-11-20",
                    "Payment Date": "2026-12-15",
                    "Div Amount": 1500.0,
                    "Div Yield": 0.15,
                    "Market Cap": None,
                    "Exchange": "HOSE",
                    "Currency": "VND",
                }
            ]
        )

        with patch(
            "app.services.events_div.services_crawler_div.scrape_dividends_vn",
            new_callable=AsyncMock,
            return_value=raw_data,
        ):
            result = asyncio.run(events_div.get_vn_upcoming_dividends_events())

        assert len(result) == 1
        dividend = result[0]
        assert dividend.symbol == "HOSE:VNM"
        assert dividend.event_category == "dividend"
        assert dividend.source_name == "VietStock"
        assert dividend.currency == "VND"
        assert dividend.link == "https://finance.vietstock.vn/VNM-thong-tin.htm"

    @pytest.mark.parametrize(
        ("public_function", "crawler_target"),
        [
            (
                events_div.get_asx_upcoming_dividends_events,
                "app.services.events_div.services_crawler_div.scrape_dividends_asx",
            ),
            (
                events_div.get_us_upcoming_dividends_events,
                "app.services.events_div.services_crawler_div.scrape_dividends_us",
            ),
            (
                events_div.get_vn_upcoming_dividends_events,
                "app.services.events_div.services_crawler_div.scrape_dividends_vn",
            ),
        ],
    )
    def test_empty_crawler_frame_returns_no_events(self, public_function, crawler_target):
        with patch(crawler_target, new_callable=AsyncMock, return_value=pd.DataFrame()):
            assert asyncio.run(public_function()) == []

    def test_noncanonical_crawler_frame_is_rejected(self):
        raw_data = pd.DataFrame(
            {
                "Ticker": ["CBA"],
                "Company": ["Commonwealth Bank"],
                "Ex-Div Date": ["2026-11-20"],
            }
        )

        with (
            patch(
                "app.services.events_div.services_crawler_div.scrape_dividends_asx",
                new_callable=AsyncMock,
                return_value=raw_data,
            ),
            pytest.raises(ValueError, match="dividend data is missing columns"),
        ):
            asyncio.run(events_div.get_asx_upcoming_dividends_events())


class TestUnloadedSupportedIndexes:
    @pytest.mark.parametrize(
        ("public_function", "crawler_target", "index_name", "raw_data"),
        [
            (
                event.get_asx_upcoming_earnings_events,
                "app.services.event.services_crawler_earnings.scrape_earnings_asx",
                "ASX20",
                pd.DataFrame(
                    {
                        "Symbol": ["CBA"],
                        "Company Name": ["Commonwealth Bank"],
                        "Announcement Date": ["2026-11-20"],
                    }
                ),
            ),
            (
                event.get_us_upcoming_earnings_events,
                "app.services.event.services_crawler_earnings.scrape_earnings_us",
                "NASDAQ100",
                pd.DataFrame(
                    {
                        "Symbol": ["AAPL"],
                        "Exchange Name": ["NASDAQ"],
                        "Company Name": ["Apple Inc."],
                        "Announcement Date": ["2026-11-20"],
                    }
                ),
            ),
            (
                events_div.get_asx_upcoming_dividends_events,
                "app.services.events_div.services_crawler_div.scrape_dividends_asx",
                "ASX20",
                _dividend_frame(
                    [
                        {
                            "Ticker": "CBA",
                            "Company": "Commonwealth Bank",
                            "Ex-Div Date": "2026-11-20",
                            "Payment Date": None,
                            "Div Amount": 2.5,
                            "Div Yield": 0.04,
                            "Market Cap": 200_000_000_000,
                            "Exchange": "ASX",
                            "Currency": "AUD",
                        }
                    ]
                ),
            ),
            (
                events_div.get_us_upcoming_dividends_events,
                "app.services.events_div.services_crawler_div.scrape_dividends_us",
                "SP500",
                _dividend_frame(
                    [
                        {
                            "Ticker": "AAPL",
                            "Company": "Apple Inc.",
                            "Ex-Div Date": "2026-11-20",
                            "Payment Date": None,
                            "Div Amount": 0.25,
                            "Div Yield": 0.005,
                            "Market Cap": 3_000_000_000_000,
                            "Exchange": "NASDAQ",
                            "Currency": "USD",
                        }
                    ]
                ),
            ),
            (
                events_div.get_vn_upcoming_dividends_events,
                "app.services.events_div.services_crawler_div.scrape_dividends_vn",
                "VN30",
                _dividend_frame(
                    [
                        {
                            "Ticker": "VNM",
                            "Company": "VNM",
                            "Ex-Div Date": "2026-11-20",
                            "Payment Date": None,
                            "Div Amount": 1500.0,
                            "Div Yield": 0.15,
                            "Market Cap": None,
                            "Exchange": "HOSE",
                            "Currency": "VND",
                        }
                    ]
                ),
            ),
        ],
        ids=["asx-earnings", "us-earnings", "asx-dividend", "us-dividend", "vn-dividend"],
    )
    def test_supported_but_unloaded_index_raises_key_error(
        self,
        public_function,
        crawler_target,
        index_name,
        raw_data,
    ):
        index_store = event.asset_utils.services_market.market_indices
        loaded_indices = dict(index_store.indices)
        loaded_indices.pop(index_name)

        with (
            patch.object(index_store, "indices", loaded_indices),
            patch(crawler_target, new_callable=AsyncMock, return_value=raw_data),
            pytest.raises(KeyError, match=index_name),
        ):
            asyncio.run(public_function(index_name))


class TestInvalidEventDates:
    @pytest.mark.parametrize(
        ("public_function", "crawler_target", "raw_data"),
        [
            (
                event.get_asx_upcoming_earnings_events,
                "app.services.event.services_crawler_earnings.scrape_earnings_asx",
                pd.DataFrame(
                    {
                        "Symbol": ["CBA"],
                        "Company Name": ["Commonwealth Bank"],
                        "Announcement Date": ["not-a-date"],
                    }
                ),
            ),
            (
                event.get_us_upcoming_earnings_events,
                "app.services.event.services_crawler_earnings.scrape_earnings_us",
                pd.DataFrame(
                    {
                        "Symbol": ["AAPL"],
                        "Exchange Name": ["NASDAQ"],
                        "Company Name": ["Apple Inc."],
                        "Announcement Date": ["not-a-date"],
                    }
                ),
            ),
            (
                events_div.get_asx_upcoming_dividends_events,
                "app.services.events_div.services_crawler_div.scrape_dividends_asx",
                _dividend_frame(
                    [
                        {
                            "Ticker": "CBA",
                            "Company": "Commonwealth Bank",
                            "Ex-Div Date": "not-a-date",
                            "Payment Date": None,
                            "Div Amount": 2.5,
                            "Div Yield": 0.04,
                            "Market Cap": 200_000_000_000,
                            "Exchange": "ASX",
                            "Currency": "AUD",
                        }
                    ]
                ),
            ),
            (
                events_div.get_us_upcoming_dividends_events,
                "app.services.events_div.services_crawler_div.scrape_dividends_us",
                _dividend_frame(
                    [
                        {
                            "Ticker": "AAPL",
                            "Company": "Apple Inc.",
                            "Ex-Div Date": "not-a-date",
                            "Payment Date": None,
                            "Div Amount": 0.25,
                            "Div Yield": 0.005,
                            "Market Cap": 3_000_000_000_000,
                            "Exchange": "NASDAQ",
                            "Currency": "USD",
                        }
                    ]
                ),
            ),
            (
                events_div.get_vn_upcoming_dividends_events,
                "app.services.events_div.services_crawler_div.scrape_dividends_vn",
                _dividend_frame(
                    [
                        {
                            "Ticker": "VNM",
                            "Company": "VNM",
                            "Ex-Div Date": "not-a-date",
                            "Payment Date": None,
                            "Div Amount": 1500.0,
                            "Div Yield": 0.15,
                            "Market Cap": None,
                            "Exchange": "HOSE",
                            "Currency": "VND",
                        }
                    ]
                ),
            ),
        ],
        ids=["asx-earnings", "us-earnings", "asx-dividend", "us-dividend", "vn-dividend"],
    )
    def test_invalid_source_date_is_surfaced(self, public_function, crawler_target, raw_data):
        with (
            patch(crawler_target, new_callable=AsyncMock, return_value=raw_data),
            pytest.raises(ValueError),
        ):
            asyncio.run(public_function())


class FakeTicker:
    def __init__(self, info, history=None):
        self.info = info
        self._history = history
        self.history_calls = []

    def history(self, **kwargs):
        self.history_calls.append(kwargs)
        return self._history.copy()


def _history_frame(*, rows=500, include_dividends=True):
    index = pd.date_range("2025-01-01", periods=rows, freq="D", tz="America/New_York")
    close = pd.Series(100.0, index=index)
    dividends = pd.Series(0.0, index=index)
    if include_dividends:
        for position in (100, 200, 300, 400):
            if position + 2 < rows:
                close.iloc[position] = 98.0
                close.iloc[position + 1] = 99.0
                close.iloc[position + 2] = 100.5
                dividends.iloc[position] = 2.0
    return pd.DataFrame(
        {
            "Open": close,
            "High": close + 1.0,
            "Low": close - 1.0,
            "Close": close,
            "Volume": 1_000_000,
            "Dividends": dividends,
        },
        index=index,
    )


def _ticker_info(**overrides):
    info = {
        "quoteType": "EQUITY",
        "regularMarketPrice": 120.0,
        "symbol": "TEST",
        "exchange": "TEST",
        "longName": "Test Company",
        "beta": 1.1,
    }
    info.update(overrides)
    return info


class TestAnalyseDividendEvent:
    def test_returns_none_for_unsupported_quote_type(self):
        ticker = FakeTicker(_ticker_info(quoteType="CURRENCY"))

        result = asyncio.run(
            events_div.analyse_dividend_event(
                ticker=ticker,
                symbol="TEST",
                ex_date="2026-11-20",
                div_amount=2.5,
            )
        )

        assert result is None
        assert ticker.history_calls == []

    @pytest.mark.parametrize(
        "ticker",
        [
            FakeTicker(_ticker_info(regularMarketPrice=0), _history_frame()),
            FakeTicker(_ticker_info(), _history_frame(rows=50)),
            FakeTicker(_ticker_info(), _history_frame(include_dividends=False)),
        ],
        ids=["missing-price", "insufficient-history", "no-past-dividends"],
    )
    def test_returns_none_for_insufficient_analysis_data(self, ticker):
        result = asyncio.run(
            events_div.analyse_dividend_event(
                ticker=ticker,
                symbol="TEST",
                ex_date="2026-11-20",
                div_amount=2.5,
            )
        )

        assert result is None

    def test_rejects_invalid_ex_dividend_date(self):
        ticker = FakeTicker(_ticker_info(), _history_frame())

        with pytest.raises(ValueError, match="ex_date"):
            asyncio.run(
                events_div.analyse_dividend_event(
                    ticker=ticker,
                    symbol="TEST",
                    ex_date="20/11/2026",
                    div_amount=2.5,
                )
            )

    def test_missing_required_history_column_is_surfaced(self):
        history = _history_frame().drop(columns=["Dividends"])
        ticker = FakeTicker(_ticker_info(), history)

        with pytest.raises(KeyError, match="Dividends"):
            asyncio.run(
                events_div.analyse_dividend_event(
                    ticker=ticker,
                    symbol="TEST",
                    ex_date="2026-11-20",
                    div_amount=2.5,
                )
            )

    def test_provider_failure_is_surfaced(self):
        ticker = FakeTicker(_ticker_info(), _history_frame())
        ticker.history = MagicMock(side_effect=RuntimeError("provider unavailable"))

        with pytest.raises(RuntimeError, match="provider unavailable"):
            asyncio.run(
                events_div.analyse_dividend_event(
                    ticker=ticker,
                    symbol="TEST",
                    ex_date="2026-11-20",
                    div_amount=2.5,
                )
            )

    def test_returns_deterministic_analysis_from_provider_history(self):
        ticker = FakeTicker(_ticker_info(), _history_frame())

        with patch("app.services.events_div.yf.Ticker") as ticker_factory:
            result = asyncio.run(
                events_div.analyse_dividend_event(
                    ticker=ticker,
                    symbol="TEST",
                    ex_date="2026-11-20",
                    div_amount=2.5,
                )
            )

        ticker_factory.assert_not_called()
        assert result is not None
        assert result.symbol == "TEST"
        assert result.exchange == "TEST"
        assert result.company_name == "Test Company"
        assert result.price == 120.0
        assert result.div_amount == 2.5
        assert math.isclose(result.div_yield, 0.05)
        assert result.num_samples == 4
        assert math.isclose(result.drop_price_min, 118.75)
        assert math.isclose(result.drop_price_max, 118.75)
        assert result.recovery_days_min == 2
        assert result.recovery_days_max == 2
        assert result.recovery_probability == 1.0
        assert result.recovery_price_min == 120.0
        assert math.isclose(result.recovery_price_max, 120.5)
        assert result.beta == 1.1
        assert result.rsi14 == 50
        assert result.avg_volume_30d == 1_000_000
        assert result.std_volume_30d == 0
        assert result.trend_60d == 0.0
