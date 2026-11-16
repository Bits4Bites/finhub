"""Unit tests for app.utils modules."""

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd
import pytest

from app.models import types
from app.services import market as services_market
from app.utils import asset, conv, finhub, yfutils
from app.utils import json as json_utils


class _YfTicker:
    def __init__(self, info):
        self.info = info


def _yf_ticker(info):
    return _YfTicker(info)


# ===========================================================================
# Tests for app.utils.conv
# ===========================================================================


class TestCountryToIso2:
    """Tests for conv.country_to_iso2."""

    @pytest.mark.parametrize(
        ("country", "expected"),
        [
            ("Australia", "AU"),
            ("us", "US"),
            ("GBR", "GB"),
            ("South Korea", "KR"),
            (" uk ", "GB"),
            ("Republic of Korea", "KR"),
            ("Hong Kong SAR", "HK"),
            ("NA", "NA"),
        ],
    )
    def test_normalizes_country_names_codes_and_market_aliases(self, country, expected):
        assert conv.country_to_iso2(country) == expected

    @pytest.mark.parametrize(
        "country",
        [
            None,
            "",
            "   ",
            "Atlantis",
            "Austraila",
            "Korea",
        ],
    )
    def test_returns_empty_for_missing_or_unrecognized_country(self, country):
        assert conv.country_to_iso2(country) == ""


class TestCountryToCurrencySymbol:
    """Tests for conv.country_to_currency_symbol."""

    @pytest.mark.parametrize(
        ("country", "expected"),
        [
            ("Australia", "$"),
            ("GB", "£"),
            ("Vietnam", "₫"),
            ("Germany", "€"),
        ],
    )
    def test_returns_locale_appropriate_currency_symbol(self, country, expected):
        assert conv.country_to_currency_symbol(country) == expected

    @pytest.mark.parametrize("country", [None, "Atlantis", "Antarctica"])
    def test_returns_empty_when_active_currency_is_unavailable(self, country):
        assert conv.country_to_currency_symbol(country) == ""


class TestCountryToCurrencyCode:
    """Tests for conv.country_to_currency_code."""

    @pytest.mark.parametrize(
        ("country", "expected"),
        [
            ("Australia", "AUD"),
            ("US", "USD"),
            ("UK", "GBP"),
            ("Republic of Korea", "KRW"),
            ("Hong Kong SAR", "HKD"),
        ],
    )
    def test_returns_primary_active_currency(self, country, expected):
        assert conv.country_to_currency_code(country) == expected

    @pytest.mark.parametrize("country", [None, "Atlantis", "Antarctica"])
    def test_returns_empty_when_active_currency_is_unavailable(self, country):
        assert conv.country_to_currency_code(country) == ""


class TestNormalizeExchangeCode:
    """Tests for conv.normalize_exchange_code."""

    @pytest.mark.parametrize(
        ("exchange", "expected"),
        [
            (" NMS ", "NASDAQ"),
            ("Nasdaq Global Select", "NASDAQ"),
            ("NYQ", "NYSE"),
            ("NYArca", "NYSE"),
            ("Cboe US", "NYSE"),
            ("New York Stock Exchange", "NYSE"),
            ("ASX", "ASX"),
        ],
    )
    def test_normalizes_known_provider_exchange_names(self, exchange, expected):
        assert conv.normalize_exchange_code(exchange) == expected

    def test_preserves_an_unrecognized_exchange_code(self):
        assert conv.normalize_exchange_code(" nymex ") == "NYMEX"


class TestToYfSymbolFormat:
    """Tests for conv.to_yf_symbol_format."""

    @pytest.mark.parametrize(
        ("symbol", "expected"),
        [
            (" asx:cba ", "CBA.AX"),
            ("HOSE:VNM", "VNM.VN"),
            ("HNX:ACB", "ACB.VN"),
            ("UPCOM:VGI", "VGI.VN"),
            ("LSE:VOD", "VOD.L"),
            ("NYSE:JPM", "JPM"),
            ("NYSEARCA:SGOV", "SGOV"),
            ("NASDAQ:AAPL", "AAPL"),
            ("cba.ax", "CBA.AX"),
            ("TSX:SHOP", "TSX:SHOP"),
            ("", ""),
        ],
    )
    def test_returns_the_provider_symbol_for_supported_and_existing_formats(self, symbol, expected):
        assert conv.to_yf_symbol_format(symbol) == expected


class TestToExchSymbFormat:
    """Tests for conv.to_exch_symb_format."""

    def test_normalizes_an_existing_exchange_symbol(self):
        assert conv.to_exch_symb_format(symbol=" asx:cba ") == "ASX:CBA"

    def test_returns_empty_without_a_ticker_or_symbol(self):
        assert conv.to_exch_symb_format() == ""

    @pytest.mark.parametrize(
        ("info", "expected"),
        [
            ({"fullExchangeName": "ASX", "symbol": "BHP.AX"}, "ASX:BHP"),
            ({"fullExchangeName": "NYSE", "symbol": "BRK.B"}, "NYSE:BRK.B"),
            ({"fullExchangeName": "LSE", "symbol": "VOD.L"}, "LSE:VOD"),
            (
                {
                    "exchange": "BTS",
                    "fullExchangeName": "Cboe US",
                    "symbol": "GOVT",
                },
                "NYSE:GOVT",
            ),
        ],
    )
    def test_converts_ticker_metadata_to_exchange_symbols(self, info, expected):
        result = conv.to_exch_symb_format(ticker=_yf_ticker(info))

        assert result == expected

    def test_ticker_takes_precedence_when_both_inputs_are_supplied(self):
        result = conv.to_exch_symb_format(
            ticker=_yf_ticker({"fullExchangeName": "ASX", "symbol": "CBA.AX"}),
            symbol="NASDAQ:AAPL",
        )

        assert result == "ASX:CBA"

    def test_uses_provider_metadata_for_a_yahoo_symbol(self, monkeypatch):
        monkeypatch.setattr(
            conv.yf,
            "Ticker",
            lambda symbol: _yf_ticker(
                {"fullExchangeName": "NMS", "symbol": symbol},
            ),
        )

        result = conv.to_exch_symb_format(symbol="AAPL")

        assert result == "NASDAQ:AAPL"

    def test_returns_provider_symbol_when_exchange_is_unavailable(self):
        assert conv.to_exch_symb_format(ticker=_yf_ticker({"symbol": "UNKNOWN"})) == "UNKNOWN"


class TestNumberToHumanFormat:
    """Tests for conv.number_to_human_format."""

    @pytest.mark.parametrize(
        ("number", "precision", "expected"),
        [
            (1_500, 2, "1.5K"),
            (2_500_000, 2, "2.5M"),
            (3_000_000_000, 2, "3B"),
            (1_200_000_000_000, 2, "1.2T"),
            (500, 2, "500"),
            (-2_500_000, 2, "-2.5M"),
            (1_234_567, 3, "1.235M"),
            (0, 2, "0"),
            (100, 0, "100"),
            (10_000, 0, "10K"),
        ],
    )
    def test_formats_compact_financial_values(self, number, precision, expected):
        assert conv.number_to_human_format(number, precision=precision) == expected

    def test_rejects_negative_precision(self):
        with pytest.raises(ValueError):
            conv.number_to_human_format(1_000, precision=-1)


class TestYyyymmddToIso:
    """Tests for conv.yyyymmdd_to_iso."""

    def test_defaults_to_utc(self):
        assert conv.yyyymmdd_to_iso("2025-01-15") == "2025-01-15 00:00:00+00:00"

    def test_uses_an_iana_timezone_name(self):
        result = conv.yyyymmdd_to_iso("2025-06-01", tz_name="Australia/Sydney")

        assert result == "2025-06-01 00:00:00+10:00"

    def test_timezone_object_takes_precedence_over_name(self):
        result = conv.yyyymmdd_to_iso(
            "2025-01-15",
            tz=ZoneInfo("UTC"),
            tz_name="Invalid/Zone",
        )

        assert result == "2025-01-15 00:00:00+00:00"

    @pytest.mark.parametrize(
        "date_value",
        ["not-a-date", "", "2025-02-30", "2025-1-2"],
    )
    def test_returns_none_for_an_invalid_date(self, date_value):
        assert conv.yyyymmdd_to_iso(date_value) is None

    def test_rejects_an_unknown_timezone_name(self):
        with pytest.raises(ZoneInfoNotFoundError):
            conv.yyyymmdd_to_iso("2025-01-15", tz_name="Invalid/Zone")


# ===========================================================================
# Tests for app.utils.json
# ===========================================================================


class TestNormalizeJsonStr:
    """Tests for json_utils.normalize_json_str."""

    @pytest.mark.parametrize(
        ("response", "expected"),
        [
            (
                ' \n```json\n{"key": "value"}\n```\n ',
                '{"key": "value"}',
            ),
            (
                '```json\r\n{\r\n  "key": "value"\r\n}\r\n```',
                '{\r\n  "key": "value"\r\n}',
            ),
            (
                "```json\n\n```",
                "",
            ),
            (
                "```json\n```",
                "",
            ),
        ],
    )
    def test_extracts_json_from_a_complete_markdown_code_block(
        self,
        response,
        expected,
    ):
        assert json_utils.normalize_json_str(response) == expected

    def test_preserves_unwrapped_json_exactly(self):
        response = ' \n{"key": "value"}\n '

        assert json_utils.normalize_json_str(response) == response

    @pytest.mark.parametrize(
        "response",
        [
            '```json\n{"key": "value"}',
            '{"key": "value"}\n```',
            '```\n{"key": "value"}\n```',
            '```JSON\n{"key": "value"}\n```',
            '```json5\n{"key": "value"}\n```',
            '```json-extra\n{"key": "value"}\n```',
            '```json {"key": "value"}\n```',
            '```json\n{"key": "value"}```',
            '```json\n{"key": "value"}\n``` trailing',
            '```json \n{"key": "value"}\n```',
            '```json\n{"key": "value"}\n ```',
            '````json\n{"key": "value"}\n````',
            '```json\n{"first": true}\n```\n```json\n{"second": true}\n```',
        ],
    )
    def test_preserves_text_without_a_complete_supported_code_block(self, response):
        assert json_utils.normalize_json_str(response) == response

    def test_extracts_payload_without_validating_json(self):
        assert json_utils.normalize_json_str("```json\nnot valid JSON\n```") == "not valid JSON"


# ===========================================================================
# Tests for app.utils.asset
# ===========================================================================


@pytest.fixture
def market_index_registry(monkeypatch):
    indices = {
        "ASX50": {},
        "ASX100": {},
        "ASX200": {},
        "ASX300": {},
        "NASDAQ100": {},
        "SP500": {},
        "SP400": {},
        "SP600": {},
        "VN30": {},
        "VN100": {},
        "HNX30": {},
    }
    monkeypatch.setattr(services_market.market_indices, "indices", indices)
    return indices


class TestDetectAssetType:
    """Tests for asset.detect_asset_type."""

    @pytest.mark.parametrize(
        ("metadata", "expected"),
        [
            ({"quote_type": "ETF"}, types.ETF_ASSET),
            ({"quote_type": "MUTUALFUND"}, types.MUTUAL_FUND_ASSET),
            ({"quote_type": "CRYPTOCURRENCY"}, types.CRYPTO_ASSET),
            ({"quote_type": "EQUITY", "sector": "Technology"}, types.STANDARD_ASSET),
            (
                {
                    "quote_type": "equity",
                    "sector": "real estate",
                    "industry": "reit - diversified",
                },
                types.REIT_ASSET,
            ),
            (
                {
                    "quote_type": "EQUITY",
                    "industry": "Asset Management",
                },
                types.LIC_ASSET,
            ),
            (
                {
                    "quote_type": "EQUITY",
                    "corp_name": "Australian Foundation Investment Company",
                },
                types.LIC_ASSET,
            ),
            (
                {
                    "quote_type": "EQUITY",
                    "corp_name": "ANZ Capital Note 7",
                },
                types.HYBRID_ASSET,
            ),
            (
                {
                    "quote_type": "EQUITY",
                    "sector": "Real Estate",
                    "industry": "REIT Asset Management",
                    "corp_name": "Hybrid Investment Note",
                },
                types.REIT_ASSET,
            ),
            (
                {
                    "quote_type": "EQUITY",
                    "industry": "Asset Management",
                    "corp_name": "Hybrid Note",
                },
                types.LIC_ASSET,
            ),
        ],
    )
    def test_classifies_supported_provider_metadata(self, metadata, expected):
        assert asset.detect_asset_type(**metadata) == expected

    @pytest.mark.parametrize(
        "metadata",
        [
            {},
            {"quote_type": "CURRENCY"},
        ],
    )
    def test_returns_other_for_missing_or_unsupported_metadata(self, metadata):
        assert asset.detect_asset_type(**metadata) == types.OTHER_ASSET


class TestIsInIndex:
    """Tests for asset.is_in_index."""

    def test_reports_constituent_membership_case_insensitively(self, market_index_registry):
        market_index_registry["ASX200"]["ASX:CBA"] = object()

        assert asset.is_in_index(index="asx200", symbol="asx:cba") is True
        assert asset.is_in_index(index="ASX200", symbol="ASX:XYZ") is False

    def test_rejects_an_index_that_is_not_loaded(self, market_index_registry):
        with pytest.raises(KeyError):
            asset.is_in_index(index="UNKNOWN", symbol="ASX:CBA")


class TestClassifyMarketCap:
    """Tests for asset.classify_market_cap."""

    def test_returns_none_for_an_unsupported_market(self, market_index_registry):
        result = asset.classify_market_cap(
            country="CA",
            exchange_symbol="TSX:SHOP",
            market_cap=100_000_000_000,
        )

        assert result == (None, None)

    def test_classifies_an_asx300_company_by_market_cap(self, market_index_registry):
        market_index_registry["ASX300"]["ASX:MID"] = object()

        result = asset.classify_market_cap(
            country="Australia",
            exchange_symbol="asx:mid",
            market_cap=5_000_000_000,
        )

        assert result == (types.MID_CAP, "ASX300")

    def test_asx100_membership_can_raise_the_market_cap_tier(self, market_index_registry):
        market_index_registry["ASX100"]["ASX:GROWTH"] = object()

        result = asset.classify_market_cap(
            country="AU",
            exchange_symbol="ASX:GROWTH",
            market_cap=500_000_000,
        )

        assert result == (types.MID_CAP, "ASX100")

    def test_an_asx_company_outside_asx300_can_move_down_a_tier(self, market_index_registry):
        result = asset.classify_market_cap(
            country="AU",
            exchange_symbol="ASX:TINY",
            market_cap=500_000_000,
        )

        assert result == (types.MICRO_CAP, None)

    def test_us_index_membership_sets_the_representative_tier(self, market_index_registry):
        market_index_registry["SP400"]["NYSE:MID"] = object()

        result = asset.classify_market_cap(
            country="US",
            exchange_symbol="NYSE:MID",
            market_cap=15_000_000_000,
        )

        assert result == (types.MID_CAP, "SP400")

    def test_us_company_outside_tracked_indices_keeps_threshold_tier(self, market_index_registry):
        result = asset.classify_market_cap(
            country="US",
            exchange_symbol="NYSE:UNTRACKED",
            market_cap=5_000_000_000,
        )

        assert result == (types.MID_CAP, None)

    def test_overlapping_memberships_use_documented_market_precedence(self, market_index_registry):
        market_index_registry["ASX50"]["ASX:OVERLAP"] = object()
        market_index_registry["ASX100"]["ASX:OVERLAP"] = object()
        market_index_registry["ASX200"]["ASX:OVERLAP"] = object()
        market_index_registry["ASX300"]["ASX:OVERLAP"] = object()
        market_index_registry["SP500"]["NYSE:OVERLAP"] = object()
        market_index_registry["SP400"]["NYSE:OVERLAP"] = object()
        market_index_registry["SP600"]["NYSE:OVERLAP"] = object()
        market_index_registry["VN30"]["HOSE:OVERLAP"] = object()
        market_index_registry["VN100"]["HOSE:OVERLAP"] = object()

        assert asset.classify_market_cap(
            country="AU",
            exchange_symbol="ASX:OVERLAP",
            market_cap=500_000_000,
        ) == (types.LARGE_CAP, "ASX50")
        assert asset.classify_market_cap(
            country="US",
            exchange_symbol="NYSE:OVERLAP",
            market_cap=15_000_000_000,
        ) == (types.SMALL_CAP, "SP600")
        assert asset.classify_market_cap(
            country="VN",
            exchange_symbol="HOSE:OVERLAP",
            market_cap=500_000_000_000,
        ) == (types.LARGE_CAP, "VN30")

    def test_vietnamese_indices_set_market_specific_tiers(self, market_index_registry):
        market_index_registry["VN30"]["HOSE:VNM"] = object()
        market_index_registry["HNX30"]["HNX:ACB"] = object()

        hose_result = asset.classify_market_cap(
            country="VN",
            exchange_symbol="HOSE:VNM",
            market_cap=5_000_000_000_000,
        )
        hnx_result = asset.classify_market_cap(
            country="Vietnam",
            exchange_symbol="HNX:ACB",
            market_cap=500_000_000_000,
        )

        assert hose_result == (types.LARGE_CAP, "VN30")
        assert hnx_result == (types.MID_CAP, "HNX30")

    def test_rejects_negative_market_cap(self, market_index_registry):
        with pytest.raises(ValueError):
            asset.classify_market_cap(
                country="US",
                exchange_symbol="NYSE:ACME",
                market_cap=-1,
            )


# ===========================================================================
# Tests for app.utils.finhub (data analysis functions)
# ===========================================================================


class TestCalcRsi:
    """Tests for finhub.calc_rsi."""

    def test_returns_index_aligned_momentum_after_warmup(self):
        index = pd.date_range("2026-01-01", periods=6, freq="D")
        data = pd.DataFrame({"Close": [100, 101, 102, 103, 104, 105]}, index=index)

        result = finhub.calc_rsi(data, period=3)

        assert isinstance(result, pd.Series)
        assert result.index.equals(index)
        assert result.iloc[:2].isna().all()
        assert result.iloc[2:].eq(100).all()

    def test_falling_prices_produce_minimum_momentum(self):
        data = pd.DataFrame({"Close": [105, 104, 103, 102, 101, 100]})

        result = finhub.calc_rsi(data, period=3)

        assert result.iloc[2:].eq(0).all()

    def test_unchanged_prices_produce_neutral_momentum(self):
        data = pd.DataFrame({"Close": [100.0] * 6})

        result = finhub.calc_rsi(data, period=3)

        assert result.iloc[:2].isna().all()
        assert result.iloc[2:].eq(50).all()

    def test_uses_simple_averages_for_mixed_price_changes(self):
        data = pd.DataFrame({"Close": [100.0, 102.0, 101.0, 104.0, 102.0]})

        result = finhub.calc_rsi(data, period=3)

        assert result.tolist() == pytest.approx(
            [float("nan"), float("nan"), 66.6666666667, 83.3333333333, 50.0],
            nan_ok=True,
        )

    @pytest.mark.parametrize("period", [0, -1])
    def test_rejects_non_positive_period(self, period):
        with pytest.raises(ValueError):
            finhub.calc_rsi(pd.DataFrame({"Close": [100, 101]}), period=period)

    def test_requires_closing_prices(self):
        with pytest.raises(KeyError):
            finhub.calc_rsi(pd.DataFrame({"Open": [100.0]}))


class TestCalcTrendSma:
    """Tests for finhub.calc_trend_sma."""

    def test_returns_relative_difference_between_simple_averages(self):
        data = pd.DataFrame({"Close": [1.0, 2.0, 3.0, 4.0]})

        result = finhub.calc_trend_sma(data, short=2, long=4)

        assert result == pytest.approx(0.4)

    def test_returns_zero_when_history_is_insufficient(self):
        data = pd.DataFrame({"Close": [100.0] * 3})

        assert finhub.calc_trend_sma(data, short=2, long=4) == 0.0

    @pytest.mark.parametrize(("short", "long"), [(0, 4), (2, 0), (-1, 4)])
    def test_rejects_non_positive_windows(self, short, long):
        with pytest.raises(ValueError):
            finhub.calc_trend_sma(pd.DataFrame({"Close": [1.0, 2.0]}), short=short, long=long)

    def test_requires_closing_prices(self):
        with pytest.raises(KeyError):
            finhub.calc_trend_sma(pd.DataFrame({"Open": [1.0, 2.0]}), short=1, long=2)


class TestCalcTrendEma:
    """Tests for finhub.calc_trend_ema."""

    def test_returns_relative_difference_between_exponential_averages(self):
        data = pd.DataFrame({"Close": [1.0, 2.0, 3.0, 4.0]})

        result = finhub.calc_trend_ema(data, short=2, long=4)

        assert result == pytest.approx(0.1467933492)

    def test_returns_zero_when_history_is_insufficient(self):
        data = pd.DataFrame({"Close": [100.0] * 3})

        assert finhub.calc_trend_ema(data, short=2, long=4) == 0.0

    @pytest.mark.parametrize(("short", "long"), [(0, 4), (2, 0), (-1, 4)])
    def test_rejects_non_positive_spans(self, short, long):
        with pytest.raises(ValueError):
            finhub.calc_trend_ema(pd.DataFrame({"Close": [1.0, 2.0]}), short=short, long=long)

    def test_requires_closing_prices(self):
        with pytest.raises(KeyError):
            finhub.calc_trend_ema(pd.DataFrame({"Open": [1.0, 2.0]}), short=1, long=2)


class TestFindVolumeSpikes:
    """Tests for finhub.find_volume_spikes."""

    def test_returns_rows_at_or_above_the_volume_threshold(self):
        index = pd.date_range("2026-01-01", periods=3, freq="D")
        data = pd.DataFrame(
            {
                "Volume": [100, 100, 400],
                "Close": [10.0, 10.5, 11.0],
            },
            index=index,
        )

        result = finhub.find_volume_spikes(data, threshold_multiplier=2)

        pd.testing.assert_frame_equal(result, data.loc[[index[2]]], check_freq=False)

    def test_returns_empty_when_no_volume_reaches_the_threshold(self):
        data = pd.DataFrame({"Volume": [100, 100, 100]})

        assert finhub.find_volume_spikes(data, threshold_multiplier=1.1).empty

    def test_requires_volume_data(self):
        with pytest.raises(KeyError):
            finhub.find_volume_spikes(pd.DataFrame({"Close": [100.0]}))


class TestAnalyzePastDividends:
    """Tests for finhub.analyze_past_dividends."""

    @staticmethod
    def _history(close_prices, dividends):
        dates = pd.date_range("2026-01-01", periods=len(close_prices), freq="D")
        return pd.DataFrame(
            {
                "Open": close_prices,
                "High": [price + 1 for price in close_prices],
                "Low": [price - 1 for price in close_prices],
                "Close": close_prices,
                "Volume": [1_000] * len(close_prices),
                "Dividends": dividends,
            },
            index=dates,
        )

    def test_returns_empty_when_history_has_no_dividends(self):
        data = self._history(
            [100.0] * 6,
            [0.0] * 6,
        )

        result = finhub.analyze_past_dividends(data)

        assert result.empty
        assert list(result.columns) == [
            "Dividends",
            "Open",
            "Close",
            "Volume",
            "DVT",
            "PreExDivPrice",
            "RecoveryDays",
            "PostExDivPeak",
            "PostExDivFloor",
            "Drop",
            "DropRatio",
        ]

    def test_returns_one_business_summary_per_dividend_event(self):
        data = self._history(
            [100.0, 98.0, 99.0, 100.0, 102.0, 101.0],
            [0.0, 2.0, 0.0, 0.0, 0.0, 0.0],
        )
        data.loc[data.index[1], ["Open", "High", "Low"]] = [97.0, 101.0, 95.0]

        result = finhub.analyze_past_dividends(data, recovery_days_threshold=3)

        assert result.index.tolist() == [data.index[1]]
        event = result.iloc[0]
        assert event["Dividends"] == 2.0
        assert event["DVT"] == pytest.approx(97_750)
        assert event["PreExDivPrice"] == 100.0
        assert event["RecoveryDays"] == 2
        assert event["PostExDivPeak"] == 102.0
        assert event["PostExDivFloor"] == 99.0
        assert event["Drop"] == 1.0
        assert event["DropRatio"] == pytest.approx(0.5)

    def test_leaves_recovery_days_empty_when_price_does_not_recover(self):
        data = self._history(
            [100.0, 98.0, 97.0, 96.0, 95.0, 94.0],
            [0.0, 2.0, 0.0, 0.0, 0.0, 0.0],
        )

        result = finhub.analyze_past_dividends(data, recovery_days_threshold=3)

        assert pd.isna(result.iloc[0]["RecoveryDays"])

    def test_recovery_does_not_depend_on_ex_date_volume(self):
        data = self._history(
            [100.0, 98.0, 100.0],
            [0.0, 2.0, 0.0],
        )
        data.loc[data.index[1], "Volume"] = 0

        result = finhub.analyze_past_dividends(data, recovery_days_threshold=3)

        assert result.iloc[0]["RecoveryDays"] == 1

    def test_first_observation_dividend_has_no_pre_event_metrics(self):
        data = self._history(
            [98.0, 100.0],
            [2.0, 0.0],
        )

        result = finhub.analyze_past_dividends(data, recovery_days_threshold=3)

        event = result.iloc[0]
        assert pd.isna(event["PreExDivPrice"])
        assert pd.isna(event["RecoveryDays"])
        assert pd.isna(event["Drop"])
        assert pd.isna(event["DropRatio"])

    def test_recovery_days_use_calendar_days_when_dates_are_missing(self):
        data = self._history(
            [100.0, 98.0, 100.0],
            [0.0, 2.0, 0.0],
        )
        data.index = pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-05"])

        result = finhub.analyze_past_dividends(data, recovery_days_threshold=4)

        assert result.iloc[0]["RecoveryDays"] == 3

    def test_floor_stops_updating_after_price_recovery(self):
        data = self._history(
            [100.0, 98.0, 100.0, 90.0],
            [0.0, 2.0, 0.0, 0.0],
        )

        result = finhub.analyze_past_dividends(data, recovery_days_threshold=2)

        event = result.iloc[0]
        assert event["RecoveryDays"] == 1
        assert event["PostExDivFloor"] == 100.0
        assert event["Drop"] == 0.0

    def test_returns_a_separate_summary_for_each_dividend_event(self):
        data = self._history(
            [100.0, 98.0, 100.0, 101.0, 97.0, 99.0, 101.0],
            [0.0, 2.0, 0.0, 0.0, 1.0, 0.0, 0.0],
        )

        result = finhub.analyze_past_dividends(
            data,
            recovery_days_threshold=2,
        )

        assert result.index.tolist() == [data.index[1], data.index[4]]
        assert result["PreExDivPrice"].tolist() == [100.0, 101.0]
        assert result["RecoveryDays"].tolist() == [1, 2]
        assert result["Drop"].tolist() == [0.0, 2.0]

    def test_recovery_can_occur_on_the_horizon_boundary(self):
        data = self._history(
            [100.0, 98.0, 99.0, 100.0],
            [0.0, 2.0, 0.0, 0.0],
        )

        result = finhub.analyze_past_dividends(
            data,
            recovery_days_threshold=2,
        )

        assert result.iloc[0]["RecoveryDays"] == 2

    @pytest.mark.parametrize("threshold", [0, -1])
    def test_rejects_non_positive_recovery_horizon(self, threshold):
        data = self._history([100.0, 98.0], [0.0, 2.0])

        with pytest.raises(ValueError):
            finhub.analyze_past_dividends(data, recovery_days_threshold=threshold)

    def test_requires_complete_market_history(self):
        with pytest.raises(KeyError):
            finhub.analyze_past_dividends(pd.DataFrame({"Dividends": [0.0]}))


class TestCalcBidAskSpreadRoll:
    """Tests for finhub.calc_bid_ask_spread_roll."""

    @pytest.mark.parametrize(
        "prices",
        [
            [100.0],
            [100.0, 101.0, 102.0, 103.0],
        ],
    )
    def test_returns_none_when_a_spread_cannot_be_estimated(self, prices):
        assert finhub.calc_bid_ask_spread_roll(pd.DataFrame({"Close": prices})) is None

    def test_returns_relative_spread_for_mean_reverting_prices(self):
        data = pd.DataFrame({"Close": [100.0, 101.0, 100.0, 101.0, 100.0]})

        result = finhub.calc_bid_ask_spread_roll(data)

        assert result is not None
        assert result > 0

    def test_relative_spread_is_unchanged_when_prices_are_rescaled(self):
        original = pd.DataFrame({"Close": [100.0, 101.0, 100.0, 101.0, 100.0]})
        rescaled = pd.DataFrame({"Close": original["Close"] * 10})

        assert finhub.calc_bid_ask_spread_roll(rescaled) == pytest.approx(finhub.calc_bid_ask_spread_roll(original))

    def test_requires_closing_prices(self):
        with pytest.raises(KeyError):
            finhub.calc_bid_ask_spread_roll(pd.DataFrame({"Open": [100.0]}))


# ===========================================================================
# Tests for app.utils.yfutils
# ===========================================================================


class TestYfutilsDetectAssetType:
    """Tests for yfutils.detect_asset_type."""

    @pytest.mark.parametrize(
        ("info", "expected"),
        [
            ({"quoteType": "ETF"}, types.ETF_ASSET),
            (
                {
                    "quoteType": "EQUITY",
                    "sector": "Real Estate",
                    "industry": "REIT - Diversified",
                },
                types.REIT_ASSET,
            ),
            ({"quoteType": "CURRENCY"}, types.OTHER_ASSET),
        ],
    )
    def test_classifies_available_provider_metadata(self, info, expected):
        assert yfutils.detect_asset_type(_yf_ticker(info)) == expected

    @pytest.mark.parametrize("ticker", [None, _yf_ticker(None), _yf_ticker({})])
    def test_returns_none_when_provider_metadata_is_unavailable(self, ticker):
        assert yfutils.detect_asset_type(ticker) is None


class TestTzFromYfTicker:
    """Tests for yfutils.tz_from_yf_ticker."""

    @pytest.mark.parametrize(
        ("info", "expected"),
        [
            ({"fullExchangeName": "ASX"}, ZoneInfo("Australia/Sydney")),
            ({"exchange": "HOSE"}, ZoneInfo("Asia/Ho_Chi_Minh")),
            ({"fullExchangeName": "HNX"}, ZoneInfo("Asia/Ho_Chi_Minh")),
            ({"fullExchangeName": "LSE"}, ZoneInfo("America/New_York")),
        ],
    )
    def test_selects_the_exchange_timezone_or_fallback(self, info, expected):
        assert yfutils.tz_from_yf_ticker(_yf_ticker(info)) == expected

    @pytest.mark.parametrize("ticker", [None, _yf_ticker(None), _yf_ticker({})])
    def test_defaults_to_new_york_when_exchange_metadata_is_unavailable(self, ticker):
        assert yfutils.tz_from_yf_ticker(ticker) == ZoneInfo("America/New_York")


class TestYfutilsIsInIndex:
    """Tests for yfutils.is_in_index."""

    def test_reports_constituent_membership(self, market_index_registry):
        market_index_registry["ASX200"]["ASX:CBA"] = object()

        assert (
            yfutils.is_in_index(
                index="asx200",
                ticker=_yf_ticker({"fullExchangeName": "ASX", "symbol": "CBA.AX"}),
            )
            is True
        )
        assert (
            yfutils.is_in_index(
                index="ASX200",
                ticker=_yf_ticker({"fullExchangeName": "ASX", "symbol": "XYZ.AX"}),
            )
            is False
        )

    def test_returns_false_without_a_usable_ticker_symbol(self, market_index_registry):
        assert yfutils.is_in_index(index="ASX200", ticker=None) is False

    def test_rejects_an_index_that_is_not_loaded(self, market_index_registry):
        with pytest.raises(KeyError):
            yfutils.is_in_index(
                index="UNKNOWN",
                ticker=_yf_ticker({"fullExchangeName": "ASX", "symbol": "CBA.AX"}),
            )


class TestLookupIndexYfStaticSymbol:
    """Tests for yfutils.lookup_index_yf_static_symbol."""

    def test_returns_the_most_specific_asx_index(self, market_index_registry):
        market_index_registry["ASX20"] = {"ASX:CBA": object()}
        market_index_registry["ASX50"]["ASX:CBA"] = object()
        market_index_registry["ASX100"]["ASX:CBA"] = object()

        result = yfutils.lookup_index_yf_static_symbol(
            ticker=_yf_ticker({"fullExchangeName": "ASX", "symbol": "CBA.AX"})
        )

        assert result == "^ATLI"

    def test_falls_back_to_all_ordinaries_for_an_untracked_asx_stock(self, market_index_registry):
        market_index_registry["ASX20"] = {}

        result = yfutils.lookup_index_yf_static_symbol(
            ticker=_yf_ticker({"fullExchangeName": "ASX", "symbol": "XYZ.AX"})
        )

        assert result == "^AORD"

    def test_selects_nasdaq_membership_or_composite_benchmark(self, market_index_registry):
        market_index_registry["NASDAQ100"]["NASDAQ:AAPL"] = object()

        member = yfutils.lookup_index_yf_static_symbol(ticker=_yf_ticker({"fullExchangeName": "NMS", "symbol": "AAPL"}))
        non_member = yfutils.lookup_index_yf_static_symbol(
            ticker=_yf_ticker({"fullExchangeName": "NMS", "symbol": "ACME"})
        )

        assert member == "^NDX"
        assert non_member == "^IXIC"

    def test_selects_nyse_membership_or_total_market_benchmark(self, market_index_registry):
        market_index_registry["SP400"]["NYSE:ACME"] = object()
        market_index_registry["SP500"]["NYSE:OVERLAP"] = object()
        market_index_registry["SP400"]["NYSE:OVERLAP"] = object()
        market_index_registry["SP600"]["NYSE:OVERLAP"] = object()

        member = yfutils.lookup_index_yf_static_symbol(
            ticker=_yf_ticker({"fullExchangeName": "NYSE", "symbol": "ACME"})
        )
        overlapping_member = yfutils.lookup_index_yf_static_symbol(
            ticker=_yf_ticker(
                {"fullExchangeName": "NYSE", "symbol": "OVERLAP"},
            )
        )
        non_member = yfutils.lookup_index_yf_static_symbol(
            ticker=_yf_ticker({"fullExchangeName": "NYSE", "symbol": "OTHER"})
        )

        assert member == "^SP400"
        assert overlapping_member == "^GSPC"
        assert non_member == "^DWCF"

    @pytest.mark.parametrize(
        "ticker",
        [
            None,
            _yf_ticker(None),
            _yf_ticker({"fullExchangeName": "LSE", "symbol": "VOD.L"}),
        ],
    )
    def test_returns_none_without_a_supported_market(self, ticker, market_index_registry):
        assert yfutils.lookup_index_yf_static_symbol(ticker=ticker) is None

    def test_requires_membership_data_for_a_supported_market(self, market_index_registry):
        market_index_registry.pop("NASDAQ100")

        with pytest.raises(KeyError):
            yfutils.lookup_index_yf_static_symbol(ticker=_yf_ticker({"fullExchangeName": "NMS", "symbol": "AAPL"}))


class TestLookupPeerYfStaticSymbol:
    """Tests for yfutils.lookup_peer_yf_static_symbol."""

    def test_selects_an_asx_sector_benchmark(self):
        result = yfutils.lookup_peer_yf_static_symbol(
            ticker=_yf_ticker(
                {
                    "fullExchangeName": "ASX",
                    "symbol": "CBA.AX",
                    "sector": "Financial Services",
                    "industry": "Banks",
                }
            )
        )

        assert result == "^AXFJ"

    def test_prefers_a_us_industry_benchmark_over_its_sector(self):
        result = yfutils.lookup_peer_yf_static_symbol(
            ticker=_yf_ticker(
                {
                    "fullExchangeName": "NMS",
                    "symbol": "URA",
                    "sector": "energy",
                    "industry": "uranium",
                }
            )
        )

        assert result == "URA"

    def test_falls_back_to_a_us_sector_benchmark(self):
        result = yfutils.lookup_peer_yf_static_symbol(
            ticker=_yf_ticker(
                {
                    "fullExchangeName": "NYSE",
                    "symbol": "ACME",
                    "sector": "Technology",
                    "industry": "Unknown",
                }
            )
        )

        assert result == "^SP500-45"

    @pytest.mark.parametrize(
        "ticker",
        [
            None,
            _yf_ticker(None),
            _yf_ticker(
                {
                    "fullExchangeName": "LSE",
                    "symbol": "VOD.L",
                    "sector": "Telecom",
                    "industry": "Wireless",
                }
            ),
        ],
    )
    def test_returns_none_without_a_supported_peer_benchmark(self, ticker):
        assert yfutils.lookup_peer_yf_static_symbol(ticker=ticker) is None


class TestYfutilsClassifyMarketCap:
    """Tests for yfutils.classify_market_cap."""

    @pytest.mark.parametrize(
        ("country", "exchange", "market_cap", "expected"),
        [
            ("United States", "NYSE", 10_000_000_000, types.LARGE_CAP),
            ("United States", "NYSE", 9_999_999_999, types.MID_CAP),
            ("United States", "NYSE", 2_000_000_000, types.MID_CAP),
            ("United States", "NYSE", 1_999_999_999, types.SMALL_CAP),
            ("United States", "NYSE", 300_000_000, types.SMALL_CAP),
            ("United States", "NYSE", 299_999_999, types.MICRO_CAP),
            ("United States", "NYSE", 50_000_000, types.MICRO_CAP),
            ("United States", "NYSE", 49_999_999, types.NANO_CAP),
            ("Vietnam", "UPCOM", 10_000_000_000_000, types.LARGE_CAP),
            ("Vietnam", "UPCOM", 9_999_999_999_999, types.MID_CAP),
            ("Vietnam", "UPCOM", 1_000_000_000_000, types.MID_CAP),
            ("Vietnam", "UPCOM", 999_999_999_999, types.SMALL_CAP),
            ("Vietnam", "UPCOM", 100_000_000_000, types.SMALL_CAP),
            ("Vietnam", "UPCOM", 99_999_999_999, types.MICRO_CAP),
            ("Vietnam", "UPCOM", 10_000_000_000, types.MICRO_CAP),
            ("Vietnam", "UPCOM", 9_999_999_999, types.NANO_CAP),
        ],
    )
    def test_applies_documented_threshold_boundaries(
        self,
        country,
        exchange,
        market_cap,
        expected,
        market_index_registry,
    ):
        ticker = _yf_ticker(
            {
                "country": country,
                "fullExchangeName": exchange,
                "symbol": "ACME",
                "marketCap": market_cap,
            }
        )

        assert yfutils.classify_market_cap(ticker) == (expected, None)

    @pytest.mark.parametrize(
        ("market_cap", "expected"),
        [
            (10_000_000_000, types.LARGE_CAP),
            (9_999_999_999, types.MID_CAP),
            (2_000_000_000, types.MID_CAP),
            (1_999_999_999, types.SMALL_CAP),
            (300_000_000, types.SMALL_CAP),
            (299_999_999, types.MICRO_CAP),
            (50_000_000, types.MICRO_CAP),
            (49_999_999, types.NANO_CAP),
        ],
    )
    def test_applies_documented_australian_threshold_boundaries(
        self,
        market_cap,
        expected,
        market_index_registry,
    ):
        market_index_registry["ASX300"]["ASX:ACME"] = object()
        ticker = _yf_ticker(
            {
                "country": "Australia",
                "fullExchangeName": "ASX",
                "symbol": "ACME.AX",
                "marketCap": market_cap,
            }
        )

        assert yfutils.classify_market_cap(ticker) == (expected, "ASX300")

    def test_index_membership_can_override_the_threshold_tier(self, market_index_registry):
        market_index_registry["ASX50"]["ASX:CBA"] = object()
        ticker = _yf_ticker(
            {
                "country": "Australia",
                "fullExchangeName": "ASX",
                "symbol": "CBA.AX",
                "marketCap": 3_000_000_000,
            }
        )

        cap, index = yfutils.classify_market_cap(ticker)

        assert cap == types.LARGE_CAP
        assert index == "ASX50"

    def test_missing_country_defaults_to_us_thresholds(self, market_index_registry):
        ticker = _yf_ticker(
            {
                "fullExchangeName": "NMS",
                "symbol": "ACME",
                "marketCap": 3_000_000_000,
            }
        )

        assert yfutils.classify_market_cap(ticker) == (types.MID_CAP, None)

    def test_vietnamese_index_membership_adjusts_the_threshold_tier(self, market_index_registry):
        market_index_registry["HNX30"]["HNX:VCS"] = object()
        ticker = _yf_ticker(
            {
                "country": "Vietnam",
                "fullExchangeName": "HNX",
                "symbol": "VCS.VN",
                "marketCap": 500_000_000_000,
            }
        )

        assert yfutils.classify_market_cap(ticker) == (types.MID_CAP, "HNX30")

    @pytest.mark.parametrize(
        "ticker",
        [
            None,
            _yf_ticker(None),
            _yf_ticker({}),
            _yf_ticker({"marketCap": None}),
        ],
    )
    def test_returns_no_classification_without_market_cap_metadata(self, ticker, market_index_registry):
        assert yfutils.classify_market_cap(ticker) == (None, None)

    def test_returns_no_classification_for_an_unsupported_country(self, market_index_registry):
        ticker = _yf_ticker(
            {
                "country": "Germany",
                "fullExchangeName": "XETRA",
                "symbol": "SAP.DE",
                "marketCap": 200_000_000_000,
            }
        )

        assert yfutils.classify_market_cap(ticker) == (None, None)

    @pytest.mark.parametrize(
        ("market_cap", "error"),
        [
            ("unknown", ValueError),
            ([], TypeError),
            (-1, ValueError),
        ],
    )
    def test_rejects_invalid_market_cap_metadata(self, market_cap, error, market_index_registry):
        ticker = _yf_ticker(
            {
                "country": "United States",
                "fullExchangeName": "NMS",
                "symbol": "ACME",
                "marketCap": market_cap,
            }
        )

        with pytest.raises(error):
            yfutils.classify_market_cap(ticker)

    def test_requires_index_membership_data_for_supported_markets(self, market_index_registry):
        market_index_registry.clear()
        ticker = _yf_ticker(
            {
                "country": "United States",
                "fullExchangeName": "NMS",
                "symbol": "ACME",
                "marketCap": 3_000_000_000,
            }
        )

        with pytest.raises(KeyError):
            yfutils.classify_market_cap(ticker)
