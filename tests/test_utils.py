"""Unit tests for app.utils modules."""

from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from app.models import types
from app.utils import asset, conv, finhub, yfutils
from app.utils import json as json_utils

# ===========================================================================
# Tests for app.utils.conv
# ===========================================================================


class TestCountryToIso2:
    """Tests for conv.country_to_iso2."""

    def test_full_country_name(self):
        assert conv.country_to_iso2("Australia") == "AU"

    def test_country_code_input(self):
        assert conv.country_to_iso2("US") == "US"

    def test_none_returns_empty(self):
        assert conv.country_to_iso2(None) == ""

    def test_empty_string_returns_empty(self):
        assert conv.country_to_iso2("") == ""

    def test_unknown_country_returns_empty(self):
        assert conv.country_to_iso2("Atlantis") == ""

    def test_vietnam(self):
        assert conv.country_to_iso2("Vietnam") == "VN"


class TestNormalizeExchangeCode:
    """Tests for conv.normalize_exchange_code."""

    def test_nms_to_nasdaq(self):
        assert conv.normalize_exchange_code("NMS") == "NASDAQ"

    def test_ngm_to_nasdaq(self):
        assert conv.normalize_exchange_code("NGM") == "NASDAQ"

    def test_nyq_to_nyse(self):
        assert conv.normalize_exchange_code("NYQ") == "NYSE"

    def test_contains_nasdaq(self):
        assert conv.normalize_exchange_code("NASDAQ Global") == "NASDAQ"

    def test_contains_ny(self):
        assert conv.normalize_exchange_code("NYArca") == "NYSE"

    def test_asx_passthrough(self):
        assert conv.normalize_exchange_code("ASX") == "ASX"

    def test_case_insensitive(self):
        assert conv.normalize_exchange_code("nms") == "NASDAQ"

    def test_whitespace_stripped(self):
        assert conv.normalize_exchange_code("  NYSE  ") == "NYSE"


class TestToYfSymbolFormat:
    """Tests for conv.to_yf_symbol_format."""

    def test_asx_exchange_to_yf(self):
        assert conv.to_yf_symbol_format("ASX:CBA") == "CBA.AX"

    def test_hose_exchange_to_yf(self):
        assert conv.to_yf_symbol_format("HOSE:VNM") == "VNM.VN"

    def test_hnx_exchange_to_yf(self):
        assert conv.to_yf_symbol_format("HNX:ACB") == "ACB.VN"

    def test_nyse_exchange_strips_prefix(self):
        assert conv.to_yf_symbol_format("NYSE:JPM") == "JPM"

    def test_nasdaq_exchange_strips_prefix(self):
        assert conv.to_yf_symbol_format("NASDAQ:AAPL") == "AAPL"

    def test_already_yf_format_passthrough(self):
        assert conv.to_yf_symbol_format("CBA.AX") == "CBA.AX"

    def test_simple_ticker_passthrough(self):
        assert conv.to_yf_symbol_format("AAPL") == "AAPL"

    def test_lowercase_uppercased(self):
        assert conv.to_yf_symbol_format("asx:cba") == "CBA.AX"


class TestToExchSymbFormat:
    """Tests for conv.to_exch_symb_format."""

    def test_already_exchange_format(self):
        assert conv.to_exch_symb_format(symbol="ASX:CBA") == "ASX:CBA"

    def test_both_none_returns_empty(self):
        assert conv.to_exch_symb_format() == ""

    def test_ticker_takes_precedence(self):
        mock_ticker = MagicMock()
        mock_ticker.info = {"fullExchangeName": "ASX", "symbol": "CBA.AX"}
        result = conv.to_exch_symb_format(ticker=mock_ticker)
        assert result == "ASX:CBA"

    def test_strips_2char_suffix(self):
        mock_ticker = MagicMock()
        mock_ticker.info = {"fullExchangeName": "ASX", "symbol": "BHP.AX"}
        result = conv.to_exch_symb_format(ticker=mock_ticker)
        assert result == "ASX:BHP"

    def test_preserves_dot_in_ticker_name(self):
        mock_ticker = MagicMock()
        mock_ticker.info = {"fullExchangeName": "NYSE", "symbol": "BRK.B"}
        result = conv.to_exch_symb_format(ticker=mock_ticker)
        # BRK.B has a 1-char suffix, so it should be preserved
        assert result == "NYSE:BRK.B"

    @patch("app.utils.conv.yf.Ticker")
    def test_symbol_without_colon_creates_ticker(self, mock_ticker_cls):
        mock_ticker_cls.return_value.info = {"fullExchangeName": "NMS", "symbol": "AAPL"}
        result = conv.to_exch_symb_format(symbol="AAPL")
        assert result == "NASDAQ:AAPL"


class TestNumberToHumanFormat:
    """Tests for conv.number_to_human_format."""

    def test_thousands(self):
        assert conv.number_to_human_format(1500) == "1.5K"

    def test_millions(self):
        assert conv.number_to_human_format(2_500_000) == "2.5M"

    def test_billions(self):
        assert conv.number_to_human_format(3_000_000_000) == "3B"

    def test_trillions(self):
        assert conv.number_to_human_format(1_200_000_000_000) == "1.2T"

    def test_small_number(self):
        assert conv.number_to_human_format(500) == "500"

    def test_negative_number(self):
        assert conv.number_to_human_format(-2_500_000) == "-2.5M"

    def test_custom_precision(self):
        assert conv.number_to_human_format(1_234_567, precision=3) == "1.235M"

    def test_zero(self):
        assert conv.number_to_human_format(0) == "0"


class TestYyyymmddToIso:
    """Tests for conv.yyyymmdd_to_iso."""

    def test_valid_date_utc(self):
        result = conv.yyyymmdd_to_iso("2025-01-15")
        assert result == "2025-01-15 00:00:00+00:00"

    def test_valid_date_with_tz(self):
        tz = ZoneInfo("Australia/Sydney")
        result = conv.yyyymmdd_to_iso("2025-06-01", tz=tz)
        assert "+10:00" in result or "+11:00" in result

    def test_valid_date_with_tz_name(self):
        result = conv.yyyymmdd_to_iso("2025-01-15", tz_name="US/Eastern")
        assert "-05:00" in result

    def test_invalid_date_returns_none(self):
        assert conv.yyyymmdd_to_iso("not-a-date") is None

    def test_empty_string_returns_none(self):
        assert conv.yyyymmdd_to_iso("") is None


# ===========================================================================
# Tests for app.utils.json
# ===========================================================================


class TestNormalizeJsonStr:
    """Tests for json_utils.normalize_json_str."""

    def test_strips_json_code_fence(self):
        input_str = '```json\n{"key": "value"}\n```'
        assert json_utils.normalize_json_str(input_str) == '{"key": "value"}'

    def test_no_fences_passthrough(self):
        input_str = '{"key": "value"}'
        assert json_utils.normalize_json_str(input_str) == '{"key": "value"}'

    def test_only_opening_fence(self):
        input_str = '```json\n{"key": "value"}'
        assert json_utils.normalize_json_str(input_str) == '{"key": "value"}'

    def test_only_closing_fence(self):
        input_str = '{"key": "value"}\n```'
        assert json_utils.normalize_json_str(input_str) == '{"key": "value"}'


# ===========================================================================
# Tests for app.utils.asset
# ===========================================================================


class TestDetectAssetType:
    """Tests for asset.detect_asset_type."""

    def test_etf(self):
        assert asset.detect_asset_type(quote_type="ETF") == types.ETF_ASSET

    def test_mutual_fund(self):
        assert asset.detect_asset_type(quote_type="MUTUALFUND") == types.MUTUAL_FUND_ASSET

    def test_cryptocurrency(self):
        assert asset.detect_asset_type(quote_type="CRYPTOCURRENCY") == types.CRYPTO_ASSET

    def test_standard_equity(self):
        assert asset.detect_asset_type(quote_type="EQUITY", sector="Technology") == types.STANDARD_ASSET

    def test_reit(self):
        result = asset.detect_asset_type(quote_type="EQUITY", sector="Real Estate", industry="REIT - Diversified")
        assert result == types.REIT_ASSET

    def test_lic_via_industry(self):
        result = asset.detect_asset_type(quote_type="EQUITY", sector="Financial Services", industry="Asset Management")
        assert result == types.LIC_ASSET

    def test_lic_via_corp_name(self):
        result = asset.detect_asset_type(quote_type="EQUITY", corp_name="Australian Foundation Investment Company")
        assert result == types.LIC_ASSET

    def test_hybrid_note(self):
        result = asset.detect_asset_type(quote_type="EQUITY", corp_name="ANZ Capital Note 7")
        assert result == types.HYBRID_ASSET

    def test_hybrid_keyword(self):
        result = asset.detect_asset_type(quote_type="EQUITY", corp_name="Macquarie Hybrid Securities")
        assert result == types.HYBRID_ASSET

    def test_unknown_quote_type(self):
        assert asset.detect_asset_type(quote_type="CURRENCY") == types.OTHER_ASSET

    def test_all_none(self):
        assert asset.detect_asset_type() == types.OTHER_ASSET


class TestIsInIndex:
    """Tests for asset.is_in_index."""

    @patch("app.utils.asset.config.market_indices")
    def test_symbol_in_index(self, mock_indices):
        mock_indices.indices = {"ASX200": {"ASX:CBA": True}}
        assert asset.is_in_index(index="ASX200", symbol="ASX:CBA") is True

    @patch("app.utils.asset.config.market_indices")
    def test_symbol_not_in_index(self, mock_indices):
        mock_indices.indices = {"ASX200": {"ASX:CBA": True}}
        assert asset.is_in_index(index="ASX200", symbol="ASX:XYZ") is False

    @patch("app.utils.asset.config.market_indices")
    def test_case_insensitive_lookup(self, mock_indices):
        mock_indices.indices = {"ASX200": {"ASX:CBA": True}}
        assert asset.is_in_index(index="asx200", symbol="asx:cba") is True


class TestClassifyMarketCap:
    """Tests for asset.classify_market_cap."""

    @patch("app.utils.asset.config.market_indices")
    def test_au_large_cap(self, mock_indices):
        mock_indices.indices = {
            "ASX50": {},
            "NASDAQ100": {},
            "SP500": {},
            "SP400": {},
            "SP600": {},
            "ASX100": {},
            "ASX200": {},
            "ASX300": {},
        }
        cap, index = asset.classify_market_cap(country="AU", exchange_symbol="ASX:BHP", market_cap=15_000_000_000)
        assert cap == types.LARGE_CAP

    @patch("app.utils.asset.config.market_indices")
    def test_au_mid_cap(self, mock_indices):
        mock_indices.indices = {
            "ASX50": {},
            "NASDAQ100": {},
            "SP500": {},
            "SP400": {},
            "SP600": {},
            "ASX100": {},
            "ASX200": {},
            "ASX300": {},
        }
        cap, index = asset.classify_market_cap(country="AU", exchange_symbol="ASX:XYZ", market_cap=5_000_000_000)
        # Mid cap outside ASX300 gets downgraded to Small
        assert cap == types.SMALL_CAP

    @patch("app.utils.asset.config.market_indices")
    def test_au_small_cap_outside_asx300_downgraded(self, mock_indices):
        mock_indices.indices = {
            "ASX50": {},
            "NASDAQ100": {},
            "SP500": {},
            "SP400": {},
            "SP600": {},
            "ASX100": {},
            "ASX200": {},
            "ASX300": {},
        }
        cap, index = asset.classify_market_cap(country="AU", exchange_symbol="ASX:TINY", market_cap=500_000_000)
        assert cap == types.MICRO_CAP  # downgraded from small because not in ASX300

    @patch("app.utils.asset.config.market_indices")
    def test_us_nasdaq100_member_large_cap(self, mock_indices):
        mock_indices.indices = {
            "ASX50": {},
            "NASDAQ100": {"NASDAQ:AAPL": True},
            "SP500": {},
            "SP400": {},
            "SP600": {},
            "ASX100": {},
            "ASX200": {},
            "ASX300": {},
        }
        cap, index = asset.classify_market_cap(
            country="US", exchange_symbol="NASDAQ:AAPL", market_cap=3_000_000_000_000
        )
        assert cap == types.LARGE_CAP
        assert index == "NASDAQ100"

    @patch("app.utils.asset.config.market_indices")
    def test_vn_large_cap(self, mock_indices):
        mock_indices.indices = {"VN30": {"HOSE:VNM": True}, "VN100": {}, "HNX30": {}}
        cap, index = asset.classify_market_cap(country="VN", exchange_symbol="HOSE:VNM", market_cap=50_000_000_000_000)
        assert cap == types.LARGE_CAP
        assert index == "VN30"

    @patch("app.utils.asset.config.market_indices")
    def test_vn_mid_cap_in_vn100(self, mock_indices):
        mock_indices.indices = {"VN30": {}, "VN100": {"HOSE:REE": True}, "HNX30": {}}
        cap, index = asset.classify_market_cap(country="VN", exchange_symbol="HOSE:REE", market_cap=20_000_000_000_000)
        assert cap == types.MID_CAP
        assert index == "VN100"


# ===========================================================================
# Tests for app.utils.finhub (data analysis functions)
# ===========================================================================


class TestCalcRsi:
    """Tests for finhub.calc_rsi."""

    def test_returns_series_with_correct_length(self):
        data = pd.DataFrame({"Close": np.random.uniform(100, 200, 30)})
        rsi = finhub.calc_rsi(data, period=14)
        assert len(rsi) == 30

    def test_rsi_between_0_and_100(self):
        data = pd.DataFrame({"Close": np.random.uniform(100, 200, 50)})
        rsi = finhub.calc_rsi(data, period=14)
        valid_rsi = rsi.dropna()
        assert (valid_rsi >= 0).all()
        assert (valid_rsi <= 100).all()

    def test_rising_prices_high_rsi(self):
        data = pd.DataFrame({"Close": list(range(100, 150))})
        rsi = finhub.calc_rsi(data, period=14)
        assert rsi.iloc[-1] > 70


class TestCalcTrendSma:
    """Tests for finhub.calc_trend_sma."""

    def test_insufficient_data_returns_zero(self):
        data = pd.DataFrame({"Close": [100.0] * 10})
        assert finhub.calc_trend_sma(data, short=50, long=100) == 0

    def test_uptrend_positive(self):
        data = pd.DataFrame({"Close": list(range(1, 201))})
        result = finhub.calc_trend_sma(data, short=50, long=100)
        assert result > 0

    def test_flat_prices_near_zero(self):
        data = pd.DataFrame({"Close": [100.0] * 200})
        result = finhub.calc_trend_sma(data, short=50, long=100)
        assert abs(result) < 0.001


class TestCalcTrendEma:
    """Tests for finhub.calc_trend_ema."""

    def test_insufficient_data_returns_zero(self):
        data = pd.DataFrame({"Close": [100.0] * 10})
        assert finhub.calc_trend_ema(data, short=21, long=55) == 0

    def test_uptrend_positive(self):
        data = pd.DataFrame({"Close": list(range(1, 201))})
        result = finhub.calc_trend_ema(data, short=21, long=55)
        assert result > 0


class TestFindVolumeSpikes:
    """Tests for finhub.find_volume_spikes."""

    def test_detects_spike(self):
        volumes = [100] * 20 + [500]
        data = pd.DataFrame({"Volume": volumes})
        spikes = finhub.find_volume_spikes(data, threshold_multiplier=2.5)
        assert len(spikes) == 1
        assert spikes.iloc[0]["Volume"] == 500

    def test_no_spikes(self):
        data = pd.DataFrame({"Volume": [100] * 20})
        spikes = finhub.find_volume_spikes(data, threshold_multiplier=2.5)
        assert len(spikes) == 0


class TestAnalyzePastDividends:
    """Tests for finhub.analyze_past_dividends."""

    def test_no_dividends_returns_empty(self):
        dates = pd.date_range("2024-01-01", periods=30, freq="D")
        data = pd.DataFrame(
            {
                "Close": [100.0] * 30,
                "Open": [100.0] * 30,
                "High": [101.0] * 30,
                "Low": [99.0] * 30,
                "Volume": [1000] * 30,
                "Dividends": [0.0] * 30,
            },
            index=dates,
        )
        result = finhub.analyze_past_dividends(data)
        assert result.empty

    def test_with_dividend_calculates_recovery(self):
        dates = pd.date_range("2024-01-01", periods=30, freq="D")
        close_prices = [100.0] * 5 + [97.0] + [98.0, 99.0, 100.0, 101.0] + [100.0] * 20
        dividends = [0.0] * 5 + [2.0] + [0.0] * 24
        data = pd.DataFrame(
            {
                "Close": close_prices,
                "Open": close_prices,
                "High": [p + 1 for p in close_prices],
                "Low": [p - 1 for p in close_prices],
                "Volume": [1000] * 30,
                "Dividends": dividends,
            },
            index=dates,
        )
        result = finhub.analyze_past_dividends(data)
        assert len(result) == 1
        assert result.iloc[0]["Dividends"] == 2.0
        assert result.iloc[0]["RecoveryDays"] is not None


class TestCalcBidAskSpreadRoll:
    """Tests for finhub.calc_bid_ask_spread_roll."""

    def test_insufficient_data_returns_none(self):
        data = pd.DataFrame({"Close": [100.0]})
        assert finhub.calc_bid_ask_spread_roll(data) is None

    def test_trending_data_returns_none(self):
        # Strongly trending data has positive covariance
        data = pd.DataFrame({"Close": list(range(100, 200))})
        result = finhub.calc_bid_ask_spread_roll(data)
        assert result is None

    def test_mean_reverting_returns_spread(self):
        # Alternating prices to create negative covariance
        prices = [100.0 + ((-1) ** i) * 0.5 for i in range(100)]
        data = pd.DataFrame({"Close": prices})
        result = finhub.calc_bid_ask_spread_roll(data)
        assert result is not None
        assert result > 0


# ===========================================================================
# Tests for app.utils.yfutils
# ===========================================================================


class TestYfutilsDetectAssetType:
    """Tests for yfutils.detect_asset_type."""

    def test_with_valid_ticker(self):
        mock_ticker = MagicMock()
        mock_ticker.info = {"quoteType": "ETF", "sector": "", "industry": "", "longName": "Vanguard ETF"}
        result = yfutils.detect_asset_type(mock_ticker)
        assert result == types.ETF_ASSET

    def test_none_ticker_returns_none(self):
        assert yfutils.detect_asset_type(None) is None

    def test_empty_info_returns_none(self):
        mock_ticker = MagicMock()
        mock_ticker.info = None
        assert yfutils.detect_asset_type(mock_ticker) is None


class TestTzFromYfTicker:
    """Tests for yfutils.tz_from_yf_ticker."""

    def test_asx_exchange_returns_sydney(self):
        mock_ticker = MagicMock()
        mock_ticker.info = {"fullExchangeName": "ASX"}
        result = yfutils.tz_from_yf_ticker(mock_ticker)
        assert result == ZoneInfo("Australia/Sydney")

    def test_hose_exchange_returns_hcm(self):
        mock_ticker = MagicMock()
        mock_ticker.info = {"fullExchangeName": "HOSE"}
        result = yfutils.tz_from_yf_ticker(mock_ticker)
        assert result == ZoneInfo("Asia/Ho_Chi_Minh")

    def test_us_exchange_returns_new_york(self):
        mock_ticker = MagicMock()
        mock_ticker.info = {"fullExchangeName": "NMS"}
        result = yfutils.tz_from_yf_ticker(mock_ticker)
        assert result == ZoneInfo("America/New_York")

    def test_none_ticker_defaults_to_new_york(self):
        result = yfutils.tz_from_yf_ticker(None)
        assert result == ZoneInfo("America/New_York")


class TestYfutilsIsInIndex:
    """Tests for yfutils.is_in_index."""

    @patch("app.utils.asset.config.market_indices")
    def test_ticker_in_index(self, mock_indices):
        mock_indices.indices = {"ASX200": {"ASX:CBA": True}}
        mock_ticker = MagicMock()
        mock_ticker.info = {"fullExchangeName": "ASX", "symbol": "CBA.AX"}
        assert yfutils.is_in_index(index="ASX200", ticker=mock_ticker) is True

    @patch("app.utils.asset.config.market_indices")
    def test_ticker_not_in_index(self, mock_indices):
        mock_indices.indices = {"ASX200": {"ASX:CBA": True}}
        mock_ticker = MagicMock()
        mock_ticker.info = {"fullExchangeName": "ASX", "symbol": "XYZ.AX"}
        assert yfutils.is_in_index(index="ASX200", ticker=mock_ticker) is False


class TestLookupIndexYfStaticSymbol:
    """Tests for yfutils.lookup_index_yf_static_symbol."""

    @patch("app.utils.asset.config.market_indices")
    def test_asx_member_returns_index_symbol(self, mock_indices):
        mock_indices.indices = {"ASX20": {"ASX:CBA": True}, "ASX50": {}, "ASX100": {}, "ASX200": {}, "ASX300": {}}
        mock_ticker = MagicMock()
        mock_ticker.info = {"fullExchangeName": "ASX", "symbol": "CBA.AX"}
        result = yfutils.lookup_index_yf_static_symbol(ticker=mock_ticker)
        assert result == "^ATLI"  # ASX20 symbol

    @patch("app.utils.asset.config.market_indices")
    def test_nasdaq100_member(self, mock_indices):
        mock_indices.indices = {"NASDAQ100": {"NASDAQ:AAPL": True}}
        mock_ticker = MagicMock()
        mock_ticker.info = {"fullExchangeName": "NMS", "symbol": "AAPL"}
        result = yfutils.lookup_index_yf_static_symbol(ticker=mock_ticker)
        assert result == "^NDX"

    @patch("app.utils.asset.config.market_indices")
    def test_nyse_sp500_member(self, mock_indices):
        mock_indices.indices = {"SP500": {"NYSE:JPM": True}, "SP400": {}, "SP600": {}}
        mock_ticker = MagicMock()
        mock_ticker.info = {"fullExchangeName": "NYSE", "symbol": "JPM"}
        result = yfutils.lookup_index_yf_static_symbol(ticker=mock_ticker)
        assert result == "^GSPC"

    @patch("app.utils.asset.config.market_indices")
    def test_unknown_exchange_returns_none(self, mock_indices):
        mock_indices.indices = {}
        mock_ticker = MagicMock()
        mock_ticker.info = {"fullExchangeName": "LSE", "symbol": "VOD.L"}
        result = yfutils.lookup_index_yf_static_symbol(ticker=mock_ticker)
        assert result is None


class TestLookupPeerYfStaticSymbol:
    """Tests for yfutils.lookup_peer_yf_static_symbol."""

    @patch("app.utils.asset.config.market_indices")
    def test_asx_financials_sector(self, mock_indices):
        mock_indices.indices = {}
        mock_ticker = MagicMock()
        mock_ticker.info = {
            "fullExchangeName": "ASX",
            "symbol": "CBA.AX",
            "sector": "Financial Services",
            "industry": "Banks",
        }
        result = yfutils.lookup_peer_yf_static_symbol(ticker=mock_ticker)
        assert result == "^AXFJ"

    @patch("app.utils.asset.config.market_indices")
    def test_unknown_sector_returns_none(self, mock_indices):
        mock_indices.indices = {}
        mock_ticker = MagicMock()
        mock_ticker.info = {"fullExchangeName": "LSE", "symbol": "VOD.L", "sector": "Telecom", "industry": "Wireless"}
        result = yfutils.lookup_peer_yf_static_symbol(ticker=mock_ticker)
        assert result is None


class TestYfutilsClassifyMarketCap:
    """Tests for yfutils.classify_market_cap."""

    @patch("app.utils.asset.config.market_indices")
    def test_large_cap_au(self, mock_indices):
        mock_indices.indices = {
            "ASX50": {"ASX:CBA": True},
            "NASDAQ100": {},
            "SP500": {},
            "SP400": {},
            "SP600": {},
            "ASX100": {},
            "ASX200": {},
            "ASX300": {},
        }
        mock_ticker = MagicMock()
        mock_ticker.info = {
            "country": "Australia",
            "fullExchangeName": "ASX",
            "symbol": "CBA.AX",
            "marketCap": 200_000_000_000,
        }
        cap, index = yfutils.classify_market_cap(mock_ticker)
        assert cap == types.LARGE_CAP
        assert index == "ASX50"

    @patch("app.utils.asset.config.market_indices")
    def test_none_ticker_defaults_to_nano(self, mock_indices):
        mock_indices.indices = {
            "ASX50": {},
            "NASDAQ100": {},
            "SP500": {},
            "SP400": {},
            "SP600": {},
            "ASX100": {},
            "ASX200": {},
            "ASX300": {},
        }
        cap, index = yfutils.classify_market_cap(None)
        # Empty info → country defaults to US, marketCap=0 → Nano
        assert cap == types.NANO_CAP
