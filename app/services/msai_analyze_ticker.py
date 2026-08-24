from __future__ import annotations

import json
import logging
import math
from datetime import UTC, datetime, timedelta
from typing import Annotated, Self

import curl_cffi.requests.exceptions as curl_requests_exceptions
import openai
import pandas as pd
import yfinance as yf
import yfinance.exceptions as yf_exceptions
from pydantic import Field, ValidationError, model_validator

from .. import config
from ..models import ai as models_ai
from ..models import ai_ticker as models_ticker
from ..models import types as models_types
from ..schemas import ai_ticker as schemas_ticker
from ..utils import ai_prompt as ai_prompt_utils
from ..utils import ai_reference as ai_reference_utils
from ..utils import asset as asset_utils
from ..utils import cache, conv, yfutils
from ..utils import finhub as finhub_utils
from . import ai_helper

_MARKET_CACHE_NAMESPACE = "ticker-analysis-market-v2"
_RESEARCH_CACHE_NAMESPACE = "ticker-analysis-research-v1"
_FORECAST_CACHE_NAMESPACE = "ticker-analysis-forecast-v1"
_RECOMMENDATION_CACHE_NAMESPACE = "ticker-analysis-recommendation-v1"
_FINAL_CACHE_NAMESPACE = "ticker-analysis-final-v1"
_CACHE_TTL = 60 * 60

_RESEARCH_TASK = "ANALYZE_TICKER_RESEARCH"
_FORECAST_TASK = "ANALYZE_TICKER_FORECAST"
_RECOMMENDATION_TASK = "ANALYZE_TICKER_RECOMMEND"

_RESEARCH_PROMPT = "ticker_research.txt"
_FORECAST_PROMPT = "ticker_forecast.txt"
_RECOMMENDATION_PROMPT = "ticker_recommendation.txt"

_RESEARCH_SCHEMA_NAME = "ticker_research"
_FORECAST_SCHEMA_NAME = "ticker_forecast"
_RECOMMENDATION_SCHEMA_NAME = "ticker_recommendation"

_HORIZON_ORDER: tuple[models_ticker.TickerForecastHorizon, ...] = (
    "OneWeek",
    "TwoWeeks",
    "OneMonth",
    "ThreeMonths",
)
_HORIZON_DAYS: dict[models_ticker.TickerForecastHorizon, int] = {
    "OneWeek": 7,
    "TwoWeeks": 14,
    "OneMonth": 30,
    "ThreeMonths": 90,
}
_HORIZON_TRADING_DAYS: dict[models_ticker.TickerForecastHorizon, int] = {
    "OneWeek": 5,
    "TwoWeeks": 10,
    "OneMonth": 21,
    "ThreeMonths": 63,
}
_RESEARCH_SECTION_NAMES = (
    "business_profile",
    "financial_performance",
    "valuation",
    "recent_developments",
    "catalysts",
    "risks",
    "market_consensus",
    "asset_specific",
)
_QUALITY_ORDER: dict[models_types.DataQuality, int] = {
    "Insufficient": 0,
    "Low": 1,
    "Medium": 2,
    "High": 3,
}


class TickerInputError(ValueError):
    pass


class TickerVerificationError(RuntimeError):
    pass


class TickerAnalysisAIError(RuntimeError):
    pass


class _ForecastEnvelope(models_ai.StrictAIModel):
    horizon: models_ticker.TickerForecastHorizon
    expected_price_min: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    expected_price_max: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    sample_count: int = Field(ge=0)
    data_gaps: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(max_length=10)

    @model_validator(mode="after")
    def validate_envelope(self) -> Self:
        if (self.expected_price_min is None) != (self.expected_price_max is None):
            raise ValueError("forecast envelope bounds must both be present or absent")
        if (
            self.expected_price_min is not None
            and self.expected_price_max is not None
            and self.expected_price_min > self.expected_price_max
        ):
            raise ValueError("forecast envelope minimum must not exceed maximum")
        if self.expected_price_min is None and not self.data_gaps:
            raise ValueError("unavailable forecast envelope requires a data gap")
        return self


class _TickerMarketBaseline(models_ai.StrictAIModel):
    snapshot: models_ticker.TickerMarketSnapshot
    forecast_envelopes: list[_ForecastEnvelope] = Field(min_length=4, max_length=4)

    @model_validator(mode="after")
    def validate_horizons(self) -> Self:
        if [envelope.horizon for envelope in self.forecast_envelopes] != list(_HORIZON_ORDER):
            raise ValueError("forecast envelopes must contain the four required horizons in order")
        return self


class _TickerResearchSourceMetadata(models_ai.ReferenceSourceMetadata):
    id: models_types.NonEmptyString = Field(max_length=4000)
    accessed_at: datetime | None

    @model_validator(mode="after")
    def validate_temporary_id(self) -> Self:
        if ai_reference_utils.normalize_url(self.id) != ai_reference_utils.normalize_url(str(self.url)):
            raise ValueError("temporary source ID must equal its HTTPS URL")
        return self


class _TickerResearchSectionResponse(models_ai.StrictAIModel):
    summary: models_types.NonEmptyString = Field(max_length=4000)
    data_quality: models_types.DataQuality
    claims: list[models_ticker.TickerEvidenceClaim] = Field(max_length=4)
    data_gaps: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(max_length=20)
    reference_ids: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(max_length=12)


class _TickerResearchResponse(models_ai.StrictAIModel):
    symbol: models_types.NonEmptyString = Field(max_length=4000)
    business_profile: _TickerResearchSectionResponse
    financial_performance: _TickerResearchSectionResponse
    valuation: _TickerResearchSectionResponse
    recent_developments: _TickerResearchSectionResponse
    catalysts: _TickerResearchSectionResponse
    risks: _TickerResearchSectionResponse
    market_consensus: _TickerResearchSectionResponse
    asset_specific: _TickerResearchSectionResponse
    data_gaps: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(max_length=20)
    references: list[_TickerResearchSourceMetadata] = Field(min_length=1, max_length=12)


class _TickerResearchDraft(models_ai.StrictAIModel):
    symbol: models_types.NonEmptyString = Field(max_length=4000)
    business_profile: models_ticker.TickerResearchSection
    financial_performance: models_ticker.TickerResearchSection
    valuation: models_ticker.TickerResearchSection
    recent_developments: models_ticker.TickerResearchSection
    catalysts: models_ticker.TickerResearchSection
    risks: models_ticker.TickerResearchSection
    market_consensus: models_ticker.TickerResearchSection
    asset_specific: models_ticker.TickerResearchSection
    data_gaps: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(max_length=20)
    references: list[_TickerResearchSourceMetadata] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def validate_references(self) -> Self:
        ai_reference_utils.validate_reference_registry(self.references, self)
        return self


class _TickerResearch(_TickerResearchDraft):
    as_of: datetime
    references: list[models_ai.ReferenceSource] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def validate_timestamp(self) -> Self:
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("research as_of must be timezone-aware")
        return self

    def to_public(self) -> models_ticker.TickerResearch:
        return models_ticker.TickerResearch.model_validate(
            self.model_dump(mode="python", exclude={"symbol", "references"})
        )


class _TickerForecastDraft(models_ai.StrictAIModel):
    horizon: models_ticker.TickerForecastHorizon
    assessment_status: models_ticker.TickerForecastAssessmentStatus
    expected_price_min: float | None = Field(gt=0, allow_inf_nan=False)
    expected_price_max: float | None = Field(gt=0, allow_inf_nan=False)
    confidence: int = Field(ge=0, le=100)
    rationale: models_types.NonEmptyString = Field(max_length=4000)
    key_drivers: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(max_length=10)
    risk_factors: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(max_length=10)
    assumptions: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(max_length=10)
    data_gaps: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(max_length=20)
    reference_ids: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(max_length=12)

    @model_validator(mode="after")
    def validate_forecast(self) -> Self:
        if len(self.reference_ids) != len(set(self.reference_ids)):
            raise ValueError("forecast reference_ids must be unique")
        if self.assessment_status == "Forecast":
            if self.expected_price_min is None or self.expected_price_max is None:
                raise ValueError("Forecast assessment requires price range")
            if self.expected_price_min > self.expected_price_max:
                raise ValueError("expected_price_min must not exceed expected_price_max")
            if not self.reference_ids:
                raise ValueError("Forecast assessment requires sourced evidence")
        else:
            if self.expected_price_min is not None or self.expected_price_max is not None:
                raise ValueError("InsufficientData assessment cannot contain price range")
            if not self.data_gaps:
                raise ValueError("InsufficientData assessment requires explicit data gaps")
        return self


class _TickerForecastResponse(models_ai.StrictAIModel):
    symbol: models_types.NonEmptyString = Field(max_length=4000)
    forecasts: list[_TickerForecastDraft] = Field(min_length=4, max_length=4)
    overall_data_quality: models_types.DataQuality
    data_gaps: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(max_length=20)

    @model_validator(mode="after")
    def validate_horizons(self) -> Self:
        if [forecast.horizon for forecast in self.forecasts] != list(_HORIZON_ORDER):
            raise ValueError("forecasts must contain the four required horizons in order")
        return self


class _ValidatedForecasts(models_ai.StrictAIModel):
    forecasts: list[models_ticker.TickerPriceForecast] = Field(min_length=4, max_length=4)
    overall_data_quality: models_types.DataQuality
    data_gaps: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(max_length=20)


class _TickerRecommendationDraft(models_ai.StrictAIModel):
    action: models_ticker.TickerRecommendationAction
    confidence: int = Field(ge=0, le=100)
    summary: models_types.NonEmptyString = Field(max_length=4000)
    buy_range: models_ticker.TickerPriceRange | None
    sell_range: models_ticker.TickerPriceRange | None
    reasoning: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(
        min_length=1,
        max_length=10,
    )
    key_conditions: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(max_length=10)
    reassessment_triggers: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(max_length=10)
    risk_warnings: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(max_length=10)
    reference_ids: list[Annotated[models_types.NonEmptyString, Field(max_length=4000)]] = Field(max_length=12)

    @model_validator(mode="after")
    def validate_ranges(self) -> Self:
        if len(self.reference_ids) != len(set(self.reference_ids)):
            raise ValueError("recommendation reference_ids must be unique")
        if self.action == "BUY":
            if self.buy_range is None or self.sell_range is not None:
                raise ValueError("BUY requires only buy_range")
        elif self.action == "SELL":
            if self.sell_range is None or self.buy_range is not None:
                raise ValueError("SELL requires only sell_range")
        elif self.buy_range is not None or self.sell_range is not None:
            raise ValueError("HOLD cannot contain buy_range or sell_range")
        if self.action != "HOLD" and not self.reference_ids:
            raise ValueError("BUY and SELL require sourced evidence")
        return self


async def ai_analyze_ticker(
    *,
    symbol: str,
    intent: str | None = None,
    current_holding: schemas_ticker.TickerHoldingInput | None = None,
) -> models_ticker.TickerAnalysis:
    """Return structured research, forecasts, and a generic recommendation for one security."""

    normalized_symbol = symbol.strip().upper()
    if not normalized_symbol:
        raise TickerInputError("Ticker symbol is required")
    normalized_intent = (intent or "").strip() or None

    baseline = await _get_market_baseline(normalized_symbol)
    holding_snapshot = _build_holding_snapshot(current_holding, baseline.snapshot)
    final_cache_key = _final_cache_key(
        baseline=baseline,
        intent=normalized_intent,
        holding_snapshot=holding_snapshot,
    )
    cached_analysis = await cache.get(final_cache_key)
    if cached_analysis is not None:
        return _cached_analysis(cached_analysis)

    research = await _research_ticker(
        baseline,
        intent=normalized_intent,
    )
    forecasts = await _forecast_ticker(
        baseline,
        research,
    )
    recommendation = await _recommend_ticker(
        baseline.snapshot,
        research,
        forecasts,
        holding_snapshot=holding_snapshot,
    )
    analysis = _build_analysis(
        baseline.snapshot,
        research,
        forecasts,
        recommendation,
        holding_snapshot=holding_snapshot,
    )
    await cache.set(
        final_cache_key,
        analysis.model_dump(mode="json"),
        ttl=_CACHE_TTL,
    )
    return analysis


async def _get_market_baseline(symbol: str) -> _TickerMarketBaseline:
    yf_symbol = conv.to_yf_symbol_format(symbol)
    cache_key = cache.generate_key(
        _MARKET_CACHE_NAMESPACE,
        yf_symbol,
        "history=2y",
        "envelope-quantiles=0.10,0.90",
    )
    cached_baseline = await cache.get(cache_key)
    if cached_baseline is not None:
        return _cached_baseline(cached_baseline)

    try:
        baseline = _build_market_baseline(yf_symbol)
    except TickerInputError:
        raise
    except (
        curl_requests_exceptions.RequestException,
        yf_exceptions.YFException,
        OSError,
    ) as exc:
        logging.exception("[Ticker Analysis] Market-data provider failed for '%s'.", symbol)
        raise TickerVerificationError("Ticker market-data verification failed") from exc
    except (IndexError, KeyError, TypeError, ValueError) as exc:
        logging.exception("[Ticker Analysis] Market-data response was invalid for '%s'.", symbol)
        raise TickerVerificationError("Ticker market-data verification returned invalid data") from exc

    await cache.set(
        cache_key,
        baseline.model_dump(mode="json"),
        ttl=_CACHE_TTL,
    )
    return baseline


def _build_market_baseline(yf_symbol: str) -> _TickerMarketBaseline:
    ticker = yf.Ticker(yf_symbol)
    info = dict(ticker.info or {})
    quote_type = str(info.get("quoteType") or "").upper()
    if quote_type not in config.ALLOWED_QUOTE_TYPES:
        raise TickerInputError("Ticker symbol is invalid or uses an unsupported security type")

    exchange = conv.normalize_exchange_code(str(info.get("fullExchangeName") or info.get("exchange") or ""))
    provider_symbol = str(info.get("symbol") or yf_symbol).upper()
    canonical_symbol = _canonical_symbol(exchange, provider_symbol)
    country = conv.country_to_iso2(str(info.get("country") or info.get("region") or ""))
    currency = str(info.get("currency") or "").strip().upper()
    if not exchange or not canonical_symbol or not country:
        raise TickerVerificationError("Ticker market identity is incomplete")
    if len(currency) != 3:
        raise TickerVerificationError("Ticker trading currency is unavailable")

    history = ticker.history(period="2y", interval="1d", auto_adjust=False)
    history = _clean_history(history)
    price_series = _adjusted_close_series(history)

    market_price = _positive_float(info.get("regularMarketPrice") or info.get("currentPrice"))
    if market_price is None and not price_series.empty:
        market_price = _positive_float(price_series.iloc[-1])
    if market_price is None:
        raise TickerVerificationError("Ticker current market price is unavailable")

    data_gaps: list[str] = []
    if len(price_series) < 64:
        data_gaps.append("Fewer than 64 valid daily price observations are available.")

    benchmark_return = _load_optional_relative_return_for_ticker(
        ticker,
        use_peer=False,
        label="market benchmark",
        data_gaps=data_gaps,
    )
    peer_return = _load_optional_relative_return_for_ticker(
        ticker,
        use_peer=True,
        label="sector or peer benchmark",
        data_gaps=data_gaps,
    )

    bid = _positive_float(info.get("bid"))
    ask = _positive_float(info.get("ask"))
    bid_ask_spread_pct = None
    if bid is not None and ask is not None and bid <= ask:
        midpoint = (bid + ask) / 2
        bid_ask_spread_pct = (ask - bid) / midpoint * 100 if midpoint > 0 else None
    elif bid is None or ask is None:
        data_gaps.append("A complete current bid/ask quote is unavailable.")

    analyst_targets = [
        _positive_float(info.get("targetLowPrice")),
        _positive_float(info.get("targetMeanPrice")),
        _positive_float(info.get("targetMedianPrice")),
        _positive_float(info.get("targetHighPrice")),
    ]
    if not any(target is not None for target in analyst_targets):
        data_gaps.append("Provider analyst price targets are unavailable.")

    snapshot = models_ticker.TickerMarketSnapshot(
        as_of=datetime.now(UTC),
        symbol=canonical_symbol,
        company_name=str(info.get("longName") or info.get("shortName") or "").strip() or None,
        asset_type=asset_utils.detect_asset_type(
            quote_type=quote_type,
            sector=str(info.get("sector") or ""),
            industry=str(info.get("industry") or ""),
            corp_name=str(info.get("longName") or info.get("shortName") or ""),
        ),
        exchange=exchange,
        country=country,
        currency=currency,
        sector=str(info.get("sector") or "").strip() or None,
        industry=str(info.get("industry") or "").strip() or None,
        market_price=market_price,
        previous_close=_positive_float(info.get("previousClose") or info.get("regularMarketPreviousClose")),
        market_day_low=_positive_float(info.get("regularMarketDayLow")),
        market_day_high=_positive_float(info.get("regularMarketDayHigh")),
        fifty_two_week_low=_positive_float(info.get("fiftyTwoWeekLow")),
        fifty_two_week_high=_positive_float(info.get("fiftyTwoWeekHigh")),
        bid=bid,
        ask=ask,
        bid_ask_spread_pct=bid_ask_spread_pct,
        market_volume=_non_negative_int(info.get("regularMarketVolume")),
        market_cap=_non_negative_int(info.get("marketCap")),
        beta=_finite_float(info.get("beta")),
        analyst_recommendation=str(info.get("recommendationKey") or "").strip() or None,
        analyst_target_low=analyst_targets[0],
        analyst_target_mean=analyst_targets[1],
        analyst_target_median=analyst_targets[2],
        analyst_target_high=analyst_targets[3],
        return_5d_pct=_historical_return_pct(price_series, 5),
        return_10d_pct=_historical_return_pct(price_series, 10),
        return_21d_pct=_historical_return_pct(price_series, 21),
        return_63d_pct=_historical_return_pct(price_series, 63),
        realized_volatility_20d_pct=_realized_volatility_pct(price_series, 20),
        realized_volatility_60d_pct=_realized_volatility_pct(price_series, 60),
        rsi14=_latest_rsi(history),
        ema_trend_pct=(_finite_float(finhub_utils.calc_trend_ema(history)) or 0.0) * 100
        if len(history) >= 55
        else None,
        atr14=_latest_atr(history),
        benchmark_return_21d_pct=benchmark_return,
        peer_return_21d_pct=peer_return,
        history_sample_count=len(price_series),
        data_gaps=list(dict.fromkeys(data_gaps))[:20],
    )
    return _TickerMarketBaseline(
        snapshot=snapshot,
        forecast_envelopes=_build_forecast_envelopes(
            price_series,
            market_price=market_price,
        ),
    )


def _canonical_symbol(exchange: str, provider_symbol: str) -> str:
    symbol = provider_symbol
    if "." in symbol:
        base, suffix = symbol.rsplit(".", 1)
        if len(suffix) == 2:
            symbol = base
    return f"{exchange}:{symbol}" if exchange and symbol else ""


def _clean_history(history: pd.DataFrame) -> pd.DataFrame:
    if history is None or history.empty or "Close" not in history:
        return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
    cleaned = history.copy()
    cleaned = cleaned.dropna(subset=["Close"])
    return cleaned[~cleaned.index.duplicated(keep="last")].sort_index()


def _adjusted_close_series(history: pd.DataFrame) -> pd.Series:
    if history.empty:
        return pd.Series(dtype="float64")
    column = "Adj Close" if "Adj Close" in history and history["Adj Close"].notna().any() else "Close"
    series = pd.to_numeric(history[column], errors="coerce").dropna()
    return series[series > 0].astype(float)


def _historical_return_pct(series: pd.Series, trading_days: int) -> float | None:
    if len(series) <= trading_days:
        return None
    previous = float(series.iloc[-trading_days - 1])
    current = float(series.iloc[-1])
    return (current / previous - 1) * 100 if previous > 0 else None


def _realized_volatility_pct(series: pd.Series, window: int) -> float | None:
    returns = series.pct_change().dropna().tail(window)
    if len(returns) < max(5, window // 2):
        return None
    volatility = float(returns.std(ddof=1)) * math.sqrt(252) * 100
    return volatility if math.isfinite(volatility) and volatility >= 0 else None


def _latest_rsi(history: pd.DataFrame) -> float | None:
    if len(history) < 15:
        return None
    values = finhub_utils.calc_rsi(history)
    latest = values.iloc[-1]
    value = _finite_float(latest)
    return value if value is not None and 0 <= value <= 100 else None


def _latest_atr(history: pd.DataFrame) -> float | None:
    if len(history) < 15 or not {"High", "Low", "Close"}.issubset(history.columns):
        return None
    previous_close = history["Close"].shift(1)
    true_range = pd.concat(
        [
            history["High"] - history["Low"],
            (history["High"] - previous_close).abs(),
            (history["Low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return _finite_float(true_range.rolling(14).mean().iloc[-1])


def _build_forecast_envelopes(
    series: pd.Series,
    *,
    market_price: float,
) -> list[_ForecastEnvelope]:
    envelopes: list[_ForecastEnvelope] = []
    for horizon in _HORIZON_ORDER:
        trading_days = _HORIZON_TRADING_DAYS[horizon]
        rolling_returns = (series / series.shift(trading_days) - 1).dropna()
        if len(rolling_returns) < 12:
            envelopes.append(
                _ForecastEnvelope(
                    horizon=horizon,
                    sample_count=len(rolling_returns),
                    data_gaps=[f"Insufficient {trading_days}-trading-day return samples for a forecast envelope."],
                )
            )
            continue
        lower_return = float(rolling_returns.quantile(0.10))
        upper_return = float(rolling_returns.quantile(0.90))
        minimum = market_price * (1 + lower_return)
        maximum = market_price * (1 + upper_return)
        if not all(math.isfinite(value) and value > 0 for value in (minimum, maximum)):
            envelopes.append(
                _ForecastEnvelope(
                    horizon=horizon,
                    sample_count=len(rolling_returns),
                    data_gaps=["Historical return distribution did not produce a positive finite price envelope."],
                )
            )
            continue
        envelopes.append(
            _ForecastEnvelope(
                horizon=horizon,
                expected_price_min=min(minimum, maximum),
                expected_price_max=max(minimum, maximum),
                sample_count=len(rolling_returns),
                data_gaps=[],
            )
        )
    return envelopes


def _load_optional_relative_return(
    symbol: str | None,
    *,
    label: str,
    data_gaps: list[str],
) -> float | None:
    if not symbol:
        data_gaps.append(f"A representative {label} is unavailable.")
        return None
    try:
        history = yf.Ticker(symbol).history(period="60d", interval="1d", auto_adjust=False)
    except (
        curl_requests_exceptions.RequestException,
        yf_exceptions.YFException,
        OSError,
    ) as exc:
        logging.warning("[Ticker Analysis] Unable to load %s '%s': %s", label, symbol, exc)
        data_gaps.append(f"The {label} price history is unavailable.")
        return None
    series = _adjusted_close_series(_clean_history(history))
    result = _historical_return_pct(series, 21)
    if result is None:
        data_gaps.append(f"The {label} lacks enough observations for a 21-day return.")
    return result


def _load_optional_relative_return_for_ticker(
    ticker: yf.Ticker,
    *,
    use_peer: bool,
    label: str,
    data_gaps: list[str],
) -> float | None:
    try:
        symbol = (
            yfutils.lookup_peer_yf_static_symbol(ticker=ticker)
            if use_peer
            else yfutils.lookup_index_yf_static_symbol(ticker=ticker)
        )
    except (
        curl_requests_exceptions.RequestException,
        yf_exceptions.YFException,
        IndexError,
        KeyError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        logging.warning("[Ticker Analysis] Unable to identify %s: %s", label, exc)
        data_gaps.append(f"A representative {label} is unavailable.")
        return None
    return _load_optional_relative_return(
        symbol,
        label=label,
        data_gaps=data_gaps,
    )


def _positive_float(value: object) -> float | None:
    result = _finite_float(value)
    return result if result is not None and result > 0 else None


def _finite_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _non_negative_int(value: object) -> int | None:
    result = _finite_float(value)
    return int(result) if result is not None and result >= 0 else None


def _build_holding_snapshot(
    holding: schemas_ticker.TickerHoldingInput | None,
    snapshot: models_ticker.TickerMarketSnapshot,
) -> models_ticker.TickerHoldingSnapshot | None:
    if holding is None:
        return None
    cost_basis = holding.num_shares * holding.avg_price
    market_value = holding.num_shares * snapshot.market_price
    profit_loss = market_value - cost_basis
    return models_ticker.TickerHoldingSnapshot(
        num_shares=holding.num_shares,
        avg_price=holding.avg_price,
        currency=snapshot.currency,
        market_price=snapshot.market_price,
        cost_basis=cost_basis,
        market_value=market_value,
        unrealized_profit_loss=profit_loss,
        unrealized_return_pct=profit_loss / cost_basis * 100,
        break_even_price=holding.avg_price,
    )


async def _research_ticker(
    baseline: _TickerMarketBaseline,
    *,
    intent: str | None,
) -> _TickerResearch:
    prompt = ai_prompt_utils.render_prompt(
        _RESEARCH_PROMPT,
        {
            "SYMBOL": baseline.snapshot.symbol,
            "ANALYSIS_FOCUS_JSON": json.dumps(intent),
            "MARKET_SNAPSHOT_JSON": baseline.snapshot.model_dump_json(),
        },
    )
    cache_key = _stage_cache_key(
        _RESEARCH_CACHE_NAMESPACE,
        prompt,
        _TickerResearchResponse,
        _RESEARCH_TASK,
    )
    cached_research = await cache.get(cache_key)
    if cached_research is not None:
        return _cached_research(cached_research)

    try:
        response = await ai_helper.ai_exec_task(
            _RESEARCH_TASK,
            prompt,
            country=baseline.snapshot.country,
            response_json_schema=_TickerResearchResponse.model_json_schema(),
            schema_name=_RESEARCH_SCHEMA_NAME,
        )
    except (OSError, ValueError, openai.APIError) as exc:
        logging.exception("[Ticker Analysis] Research provider call failed.")
        raise TickerAnalysisAIError("Ticker research provider failed") from exc
    if response.is_error:
        logging.error("[Ticker Analysis] Research failed: %s", response.error_msg)
        raise TickerAnalysisAIError("Ticker research failed")

    try:
        raw_research = _TickerResearchResponse.model_validate_json(response.completion)
        if raw_research.symbol.strip().upper() != baseline.snapshot.symbol:
            raise ValueError("research returned a different symbol")
        repaired_research = _repair_research_references(raw_research)
        research = _finalize_research_references(
            repaired_research,
            response.citation_urls,
            accessed_at=datetime.now(UTC),
        )
    except (TypeError, ValueError, ValidationError) as exc:
        raise TickerAnalysisAIError("Ticker research returned invalid structured data") from exc

    await cache.set(
        cache_key,
        research.model_dump(mode="json"),
        ttl=_CACHE_TTL,
    )
    return research


def _repair_research_references(research: _TickerResearchResponse) -> _TickerResearchDraft:
    research_data = research.model_dump()
    registry_ids = {reference.id for reference in research.references}
    missing_ids: set[str] = set()
    dropped_claims = 0

    for section_name in _RESEARCH_SECTION_NAMES:
        section = research_data[section_name]
        original_claim_count = len(section["claims"])
        declared_section_ids = set(section["reference_ids"])
        valid_claims = []
        used_section_ids: list[str] = []
        section_missing_ids: set[str] = set()
        for claim in section["claims"]:
            unknown_ids = set(claim["reference_ids"]) - registry_ids
            missing_ids.update(unknown_ids)
            section_missing_ids.update(unknown_ids)
            valid_ids = [reference_id for reference_id in claim["reference_ids"] if reference_id in registry_ids]
            if not valid_ids:
                dropped_claims += 1
                continue
            claim["reference_ids"] = list(dict.fromkeys(valid_ids))
            valid_claims.append(claim)
            used_section_ids.extend(claim["reference_ids"])

        section_missing_ids.update(declared_section_ids - set(used_section_ids))
        section["claims"] = valid_claims
        section["reference_ids"] = list(dict.fromkeys(used_section_ids))
        if section_missing_ids or len(valid_claims) < original_claim_count:
            missing_text = ", ".join(sorted(section_missing_ids)) or "none"
            section["data_gaps"] = [
                *section["data_gaps"][:19],
                f"Ignored unsupported source links: {missing_text}.",
            ]
            if len(valid_claims) < original_claim_count:
                section["summary"] = (
                    " ".join(claim["text"] for claim in valid_claims)
                    or "No supported sourced claims were available for this section."
                )[:4000]
                section["data_quality"] = "Low" if valid_claims else "Insufficient"
            elif _QUALITY_ORDER[section["data_quality"]] > _QUALITY_ORDER["Medium"]:
                section["data_quality"] = "Medium"

    used_ids = ai_reference_utils.collect_reference_ids(research_data)
    unused_registry_ids = registry_ids - used_ids
    research_data["references"] = [
        reference for reference in research_data["references"] if reference["id"] in used_ids
    ]
    if not research_data["references"]:
        raise ValueError("research contains no supported sourced claims")
    if missing_ids or dropped_claims or unused_registry_ids:
        warning_parts = []
        if missing_ids:
            warning_parts.append(f"Ignored unknown source IDs: {', '.join(sorted(missing_ids))}.")
        if unused_registry_ids:
            warning_parts.append(f"Pruned unused sources: {', '.join(sorted(unused_registry_ids))}.")
        if dropped_claims:
            warning_parts.append(f"Removed {dropped_claims} unsupported claim(s).")
        warning = " ".join(warning_parts)
        research_data["data_gaps"] = [*research_data["data_gaps"][:19], warning]
        logging.warning("[Ticker Analysis] %s", warning)
    return _TickerResearchDraft.model_validate(research_data)


def _finalize_research_references(
    research: _TickerResearchDraft,
    citation_urls: list[str],
    *,
    accessed_at: datetime,
) -> _TickerResearch:
    canonicalized = ai_reference_utils.canonicalize_reference_sources(
        research.references,
        citation_urls,
        accessed_at=accessed_at,
    )
    research_data = ai_reference_utils.remap_reference_ids(research, canonicalized.id_map)
    if not isinstance(research_data, dict):
        raise TypeError("Remapped ticker research must be an object")
    research_data["as_of"] = accessed_at
    research_data["references"] = [reference.model_dump(mode="python") for reference in canonicalized.references]
    return _TickerResearch.model_validate(research_data)


async def _forecast_ticker(
    baseline: _TickerMarketBaseline,
    research: _TickerResearch,
) -> _ValidatedForecasts:
    prompt = ai_prompt_utils.render_prompt(
        _FORECAST_PROMPT,
        {
            "SYMBOL": baseline.snapshot.symbol,
            "MARKET_BASELINE_JSON": baseline.model_dump_json(),
            "RESEARCH_JSON": research.model_dump_json(),
        },
    )
    cache_key = _stage_cache_key(
        _FORECAST_CACHE_NAMESPACE,
        prompt,
        _TickerForecastResponse,
        _FORECAST_TASK,
    )
    cached_forecasts = await cache.get(cache_key)
    if cached_forecasts is not None:
        return _cached_forecasts(cached_forecasts)

    try:
        response = await ai_helper.ai_exec_task(
            _FORECAST_TASK,
            prompt,
            country=baseline.snapshot.country,
            response_json_schema=_TickerForecastResponse.model_json_schema(),
            schema_name=_FORECAST_SCHEMA_NAME,
        )
    except (OSError, ValueError, openai.APIError) as exc:
        logging.exception("[Ticker Analysis] Forecast provider call failed.")
        raise TickerAnalysisAIError("Ticker forecast provider failed") from exc
    if response.is_error:
        logging.error("[Ticker Analysis] Forecast failed: %s", response.error_msg)
        raise TickerAnalysisAIError("Ticker forecast failed")

    try:
        draft = _TickerForecastResponse.model_validate_json(response.completion)
        if draft.symbol.strip().upper() != baseline.snapshot.symbol:
            raise ValueError("forecast returned a different symbol")
        forecasts = _finalize_forecasts(draft, baseline, research)
    except (ValueError, ValidationError) as exc:
        raise TickerAnalysisAIError("Ticker forecast returned invalid structured data") from exc

    await cache.set(
        cache_key,
        forecasts.model_dump(mode="json"),
        ttl=_CACHE_TTL,
    )
    return forecasts


def _finalize_forecasts(
    draft: _TickerForecastResponse,
    baseline: _TickerMarketBaseline,
    research: _TickerResearch,
) -> _ValidatedForecasts:
    known_reference_ids = {reference.id for reference in research.references}
    unknown_reference_ids = ai_reference_utils.collect_reference_ids(draft) - known_reference_ids
    if unknown_reference_ids:
        raise ValueError(f"forecast contains unknown reference IDs: {sorted(unknown_reference_ids)}")

    envelope_by_horizon = {envelope.horizon: envelope for envelope in baseline.forecast_envelopes}
    public_forecasts: list[models_ticker.TickerPriceForecast] = []
    forecast_count = 0
    for item in draft.forecasts:
        envelope = envelope_by_horizon[item.horizon]
        price_min = item.expected_price_min
        price_max = item.expected_price_max
        if item.assessment_status == "Forecast":
            forecast_count += 1
            if envelope.expected_price_min is None or envelope.expected_price_max is None:
                raise ValueError(f"{item.horizon} forecast lacks a deterministic envelope")
            if price_min < envelope.expected_price_min - 1e-6 or price_max > envelope.expected_price_max + 1e-6:
                raise ValueError(f"{item.horizon} forecast is outside its deterministic envelope")
            return_min = (price_min / baseline.snapshot.market_price - 1) * 100
            return_max = (price_max / baseline.snapshot.market_price - 1) * 100
            direction = _forecast_direction(
                price_min,
                price_max,
                market_price=baseline.snapshot.market_price,
            )
        else:
            return_min = None
            return_max = None
            direction = "InsufficientData"
        public_forecasts.append(
            models_ticker.TickerPriceForecast(
                horizon=item.horizon,
                horizon_days=_HORIZON_DAYS[item.horizon],
                period_end=baseline.snapshot.as_of.date() + timedelta(days=_HORIZON_DAYS[item.horizon]),
                assessment_status=item.assessment_status,
                direction=direction,
                expected_price_min=price_min,
                expected_price_max=price_max,
                expected_return_min_pct=return_min,
                expected_return_max_pct=return_max,
                confidence=item.confidence if item.assessment_status == "Forecast" else min(item.confidence, 25),
                rationale=item.rationale,
                key_drivers=item.key_drivers,
                risk_factors=item.risk_factors,
                assumptions=item.assumptions,
                data_gaps=item.data_gaps,
                reference_ids=item.reference_ids,
            )
        )
    overall_data_quality = draft.overall_data_quality
    if forecast_count == 0:
        overall_data_quality = "Insufficient"
    elif forecast_count <= 2:
        overall_data_quality = min(overall_data_quality, "Low", key=_QUALITY_ORDER.__getitem__)
    elif forecast_count == 3:
        overall_data_quality = min(overall_data_quality, "Medium", key=_QUALITY_ORDER.__getitem__)
    return _ValidatedForecasts(
        forecasts=public_forecasts,
        overall_data_quality=overall_data_quality,
        data_gaps=draft.data_gaps,
    )


def _forecast_direction(
    minimum: float,
    maximum: float,
    *,
    market_price: float,
) -> models_ticker.TickerPriceDirection:
    up_threshold = market_price * 1.01
    down_threshold = market_price * 0.99
    if minimum > up_threshold:
        return "Up"
    if maximum < down_threshold:
        return "Down"
    if minimum <= market_price <= maximum and (maximum - minimum) / market_price > 0.04:
        return "Mixed"
    return "Flat"


async def _recommend_ticker(
    snapshot: models_ticker.TickerMarketSnapshot,
    research: _TickerResearch,
    forecasts: _ValidatedForecasts,
    *,
    holding_snapshot: models_ticker.TickerHoldingSnapshot | None,
) -> models_ticker.TickerRecommendation:
    overall_data_quality = _overall_data_quality(research, forecasts)
    prompt = ai_prompt_utils.render_prompt(
        _RECOMMENDATION_PROMPT,
        {
            "SYMBOL": snapshot.symbol,
            "MARKET_SNAPSHOT_JSON": snapshot.model_dump_json(),
            "HOLDING_CONTEXT_JSON": holding_snapshot.model_dump_json() if holding_snapshot else "null",
            "RESEARCH_JSON": research.model_dump_json(),
            "FORECASTS_JSON": forecasts.model_dump_json(),
            "OVERALL_DATA_QUALITY": overall_data_quality,
        },
    )
    cache_key = _stage_cache_key(
        _RECOMMENDATION_CACHE_NAMESPACE,
        prompt,
        _TickerRecommendationDraft,
        _RECOMMENDATION_TASK,
    )
    cached_recommendation = await cache.get(cache_key)
    if cached_recommendation is not None:
        return _cached_recommendation(cached_recommendation)

    try:
        response = await ai_helper.ai_exec_task(
            _RECOMMENDATION_TASK,
            prompt,
            country=snapshot.country,
            response_json_schema=_TickerRecommendationDraft.model_json_schema(),
            schema_name=_RECOMMENDATION_SCHEMA_NAME,
        )
    except (OSError, ValueError, openai.APIError) as exc:
        logging.exception("[Ticker Analysis] Recommendation provider call failed.")
        raise TickerAnalysisAIError("Ticker recommendation provider failed") from exc
    if response.is_error:
        logging.error("[Ticker Analysis] Recommendation failed: %s", response.error_msg)
        raise TickerAnalysisAIError("Ticker recommendation failed")

    try:
        draft = _TickerRecommendationDraft.model_validate_json(response.completion)
        recommendation = _finalize_recommendation(
            draft,
            snapshot,
            research,
            forecasts,
            overall_data_quality=overall_data_quality,
            holding_snapshot=holding_snapshot,
        )
    except (ValueError, ValidationError) as exc:
        raise TickerAnalysisAIError("Ticker recommendation returned invalid structured data") from exc

    await cache.set(
        cache_key,
        recommendation.model_dump(mode="json"),
        ttl=_CACHE_TTL,
    )
    return recommendation


def _finalize_recommendation(
    draft: _TickerRecommendationDraft,
    snapshot: models_ticker.TickerMarketSnapshot,
    research: _TickerResearch,
    forecasts: _ValidatedForecasts,
    *,
    overall_data_quality: models_types.DataQuality,
    holding_snapshot: models_ticker.TickerHoldingSnapshot | None,
) -> models_ticker.TickerRecommendation:
    known_reference_ids = {reference.id for reference in research.references}
    unknown_reference_ids = set(draft.reference_ids) - known_reference_ids
    if unknown_reference_ids:
        raise ValueError(f"recommendation contains unknown reference IDs: {sorted(unknown_reference_ids)}")
    if overall_data_quality == "Insufficient" and draft.action != "HOLD":
        raise ValueError("Insufficient analysis can only recommend HOLD")

    available_prices = [snapshot.market_price]
    for forecast in forecasts.forecasts:
        if forecast.expected_price_min is not None and forecast.expected_price_max is not None:
            available_prices.extend([forecast.expected_price_min, forecast.expected_price_max])
    selected_range = draft.buy_range if draft.action == "BUY" else draft.sell_range
    if selected_range is not None:
        if selected_range.currency != snapshot.currency:
            raise ValueError("recommendation range currency does not match market snapshot")
        lower_limit = min(available_prices) * 0.75
        upper_limit = max(available_prices) * 1.25
        if selected_range.minimum < lower_limit or selected_range.maximum > upper_limit:
            raise ValueError("recommendation range is inconsistent with current and forecast prices")

    return models_ticker.TickerRecommendation(
        action=draft.action,
        scope="ExistingHolding" if holding_snapshot else "NewPosition",
        confidence=min(draft.confidence, 25) if overall_data_quality == "Insufficient" else draft.confidence,
        summary=draft.summary,
        buy_range=draft.buy_range,
        sell_range=draft.sell_range,
        reasoning=draft.reasoning,
        key_conditions=draft.key_conditions,
        reassessment_triggers=draft.reassessment_triggers,
        risk_warnings=draft.risk_warnings,
        reference_ids=draft.reference_ids,
    )


def _build_analysis(
    snapshot: models_ticker.TickerMarketSnapshot,
    research: _TickerResearch,
    forecasts: _ValidatedForecasts,
    recommendation: models_ticker.TickerRecommendation,
    *,
    holding_snapshot: models_ticker.TickerHoldingSnapshot | None,
) -> models_ticker.TickerAnalysis:
    public_research = research.to_public()
    references = research.references
    unverified_count = sum(not reference.is_verified for reference in references)
    warnings = []
    if unverified_count:
        warnings.append(f"{unverified_count} cited research source(s) could not be provider-verified.")

    overall_data_quality = _overall_data_quality(research, forecasts)
    data_gaps = list(
        dict.fromkeys(
            [
                *snapshot.data_gaps,
                *public_research.data_gaps,
                *forecasts.data_gaps,
                *(gap for forecast in forecasts.forecasts for gap in forecast.data_gaps),
            ]
        )
    )[:20]
    try:
        return models_ticker.TickerAnalysis(
            as_of=datetime.now(UTC),
            analysis_status="CompleteWithWarnings" if warnings else "Complete",
            symbol=snapshot.symbol,
            company_name=snapshot.company_name,
            asset_type=snapshot.asset_type,
            exchange=snapshot.exchange,
            country=snapshot.country,
            currency=snapshot.currency,
            market_snapshot=snapshot,
            holding_snapshot=holding_snapshot,
            research=public_research,
            forecasts=forecasts.forecasts,
            recommendation=recommendation,
            overall_data_quality=overall_data_quality,
            data_gaps=data_gaps,
            validation_warnings=warnings,
            references=references,
        )
    except ValidationError as exc:
        raise TickerAnalysisAIError("Ticker analysis failed final validation") from exc


def _overall_data_quality(
    research: _TickerResearch,
    forecasts: _ValidatedForecasts,
) -> models_types.DataQuality:
    public_research = research.to_public()
    if forecasts.overall_data_quality == "Insufficient":
        return "Insufficient"
    research_qualities = [
        getattr(public_research, section_name).data_quality for section_name in _RESEARCH_SECTION_NAMES
    ]
    research_score = sum(_QUALITY_ORDER[quality] for quality in research_qualities) / len(research_qualities)
    average_score = (_QUALITY_ORDER[forecasts.overall_data_quality] + research_score) / 2
    if average_score >= 2.5:
        return "High"
    if average_score >= 1.5:
        return "Medium"
    if average_score >= 0.5:
        return "Low"
    return "Insufficient"


def _stage_cache_key(
    namespace: str,
    prompt: str,
    response_model: type[models_ai.StrictAIModel],
    task_id: str,
) -> str:
    return cache.generate_hourly_key(
        namespace,
        prompt,
        json.dumps(response_model.model_json_schema(), sort_keys=True),
        _task_cache_identity(task_id),
    )


def _final_cache_key(
    *,
    baseline: _TickerMarketBaseline,
    intent: str | None,
    holding_snapshot: models_ticker.TickerHoldingSnapshot | None,
) -> str:
    return cache.generate_hourly_key(
        _FINAL_CACHE_NAMESPACE,
        json.dumps(
            {
                "baseline": baseline.model_dump(mode="json"),
                "intent": intent,
                "holding_snapshot": holding_snapshot.model_dump(mode="json") if holding_snapshot else None,
            },
            sort_keys=True,
        ),
        ai_prompt_utils.load_prompt(_RESEARCH_PROMPT),
        ai_prompt_utils.load_prompt(_FORECAST_PROMPT),
        ai_prompt_utils.load_prompt(_RECOMMENDATION_PROMPT),
        json.dumps(_TickerResearchResponse.model_json_schema(), sort_keys=True),
        json.dumps(_TickerForecastResponse.model_json_schema(), sort_keys=True),
        json.dumps(_TickerRecommendationDraft.model_json_schema(), sort_keys=True),
        json.dumps(models_ticker.TickerAnalysis.model_json_schema(), sort_keys=True),
        _task_cache_identity(_RESEARCH_TASK),
        _task_cache_identity(_FORECAST_TASK),
        _task_cache_identity(_RECOMMENDATION_TASK),
    )


def _task_cache_identity(task_id: str) -> str:
    task_config = config.settings_llm_task.tasks.get(task_id)
    if task_config is None:
        return task_id
    return json.dumps(
        {
            "task": task_id,
            "config": task_config.model_dump(mode="json"),
        },
        sort_keys=True,
    )


def _cached_baseline(value: object) -> _TickerMarketBaseline:
    try:
        return (
            value.model_copy(deep=True)
            if isinstance(value, _TickerMarketBaseline)
            else _TickerMarketBaseline.model_validate(value)
        )
    except (TypeError, ValidationError) as exc:
        raise TickerVerificationError("Ticker market cache contains an invalid value") from exc


def _cached_research(value: object) -> _TickerResearch:
    try:
        return (
            value.model_copy(deep=True) if isinstance(value, _TickerResearch) else _TickerResearch.model_validate(value)
        )
    except (TypeError, ValidationError) as exc:
        raise TickerAnalysisAIError("Ticker research cache contains an invalid value") from exc


def _cached_forecasts(value: object) -> _ValidatedForecasts:
    try:
        return (
            value.model_copy(deep=True)
            if isinstance(value, _ValidatedForecasts)
            else _ValidatedForecasts.model_validate(value)
        )
    except (TypeError, ValidationError) as exc:
        raise TickerAnalysisAIError("Ticker forecast cache contains an invalid value") from exc


def _cached_recommendation(value: object) -> models_ticker.TickerRecommendation:
    try:
        return (
            value.model_copy(deep=True)
            if isinstance(value, models_ticker.TickerRecommendation)
            else models_ticker.TickerRecommendation.model_validate(value)
        )
    except (TypeError, ValidationError) as exc:
        raise TickerAnalysisAIError("Ticker recommendation cache contains an invalid value") from exc


def _cached_analysis(value: object) -> models_ticker.TickerAnalysis:
    try:
        return (
            value.model_copy(deep=True)
            if isinstance(value, models_ticker.TickerAnalysis)
            else models_ticker.TickerAnalysis.model_validate(value)
        )
    except (TypeError, ValidationError) as exc:
        raise TickerAnalysisAIError("Ticker analysis cache contains an invalid value") from exc
