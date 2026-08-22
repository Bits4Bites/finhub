from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import openai
import pandas as pd
import yfinance as yf
from pydantic import Field, ValidationError, model_validator

from .. import config
from ..models import ai as models_ai
from ..models import events_dividends as models_events_dividends
from ..models import types
from ..utils import ai_prompt as ai_prompt_utils
from ..utils import ai_reference as ai_reference_utils
from ..utils import cache, conv, yfutils
from ..utils import finhub as finhub_utils
from . import ai_helper

_ALLOWED_QUOTE_TYPES = frozenset({"EQUITY", "ETF", "MUTUALFUND"})
_ANALYSIS_CACHE_NAMESPACE = "dividend-event-analysis-v2"
_ANALYSIS_PROMPT_VERSION = "6"
_FAILED_ANALYSIS_CACHE_TTL = 5 * 60
_DEFAULT_HOLDING_PERIOD_DAYS = 28
_MINIMUM_COMPARABLE_EVENTS = 4
_MINIMUM_RECOMMENDATION_CONFIDENCE = 60
_MINIMUM_PROBABILITY_ADVANTAGE = 0.10
_RESEARCH_TASK = "ANALYZE_DIV_EVENT_RESEARCH"
_ASSESS_TASK = "ANALYZE_DIV_EVENT_ASSESS"
_RESEARCH_SCHEMA_NAME = "dividend_event_research"
_ASSESSMENT_SCHEMA_NAME = "dividend_event_assessment"
_RESEARCH_SECTION_NAMES = ("dividend_terms", "issuer_outlook", "event_risks", "market_context")


class DividendEventInputError(ValueError):
    pass


class DividendEventInsufficientDataError(ValueError):
    pass


class DividendEventAIError(RuntimeError):
    pass


@dataclass(frozen=True)
class _DividendSample:
    open_drop_ratio: float
    close_drop_ratio: float
    intraday_low_drop_ratio: float
    drawdown_ratio: float
    pre_ex_close_recovery_days: int | None
    capture_break_even_recovery_days: int | None
    discount_break_even_recovery_days: int | None


class _DividendResearchSection(models_events_dividends.DividendEvidenceSection):
    facts: list[models_events_dividends.DividendEvidenceClaim] = Field(max_length=3)


class _DividendResearchSourceMetadata(models_ai.ReferenceSourceMetadata):
    id: types.NonEmptyString = Field(max_length=4000)
    accessed_at: datetime | None

    @model_validator(mode="after")
    def validate_temporary_id(self) -> Self:
        if ai_reference_utils.normalize_url(self.id) != ai_reference_utils.normalize_url(str(self.url)):
            raise ValueError("temporary source ID must equal its HTTPS URL")
        return self


class _DividendResearchResponse(models_ai.StrictAIModel):
    symbol: types.NonEmptyString = Field(max_length=4000)
    as_of: datetime
    dividend_terms: _DividendResearchSection
    issuer_outlook: _DividendResearchSection
    event_risks: _DividendResearchSection
    market_context: _DividendResearchSection
    references: list[_DividendResearchSourceMetadata] = Field(min_length=1, max_length=6)


class _DividendResearchDraft(_DividendResearchResponse):
    @model_validator(mode="after")
    def validate_references(self) -> Self:
        ai_reference_utils.validate_reference_registry(self.references, self)
        return self


class _DividendResearch(_DividendResearchDraft):
    references: list[models_ai.ReferenceSource] = Field(min_length=1, max_length=6)


class _DividendStrategyAssessmentDraft(models_events_dividends.DividendStrategyAssessment):
    success_probability: float | None = Field(ge=0, le=1, allow_inf_nan=False)


class _DividendAssessmentDraft(models_ai.StrictAIModel):
    symbol: types.NonEmptyString = Field(max_length=4000)
    as_of: datetime
    overall_data_quality: types.DataQuality
    evidence_adjusted_ex_date_close_drop: models_events_dividends.DividendDropEstimate | None
    evidence_adjusted_pre_ex_close_recovery: models_events_dividends.DividendRecoveryEstimate | None
    evidence_adjusted_capture_break_even_recovery: models_events_dividends.DividendRecoveryEstimate | None
    evidence_adjusted_discount_break_even_recovery: models_events_dividends.DividendRecoveryEstimate | None
    dividend_capture: _DividendStrategyAssessmentDraft
    post_dividend_discount: _DividendStrategyAssessmentDraft
    comparison_rationale: types.NonEmptyString = Field(max_length=4000)
    comparison_reference_ids: list[Annotated[types.NonEmptyString, Field(max_length=4000)]] = Field(
        min_length=1,
        max_length=6,
    )

    @model_validator(mode="after")
    def validate_strategies(self) -> Self:
        if self.dividend_capture.strategy != "DividendCapture":
            raise ValueError("dividend_capture must assess DividendCapture")
        if self.post_dividend_discount.strategy != "PostDividendDiscount":
            raise ValueError("post_dividend_discount must assess PostDividendDiscount")
        return self


@dataclass(frozen=True)
class _DividendAssessmentResult:
    assessment: _DividendAssessmentDraft
    validation_warnings: tuple[str, ...]


async def ai_analyze_div_event(
    *,
    symbol: str,
    ex_date: date,
    dividend_amount: float,
    transaction_costs: models_events_dividends.DividendTransactionCosts | None = None,
    holding_period_days: int = _DEFAULT_HOLDING_PERIOD_DAYS,
) -> models_events_dividends.DividendEventAnalysis:
    costs = transaction_costs or models_events_dividends.DividendTransactionCosts()
    _validate_request_values(
        symbol,
        ex_date,
        dividend_amount,
        costs,
        holding_period_days,
    )

    normalized_input_symbol = symbol.strip().upper()
    ticker = yf.Ticker(conv.to_yf_symbol_format(normalized_input_symbol))
    info = ticker.info or {}
    if str(info.get("quoteType") or "").upper() not in _ALLOWED_QUOTE_TYPES:
        raise DividendEventInputError("Unsupported or unknown asset type")

    raw_history = ticker.history(period="5y", interval="1d", auto_adjust=False)
    timezone = _resolve_exchange_timezone(info, raw_history)
    history = _normalize_history(
        raw_history,
        timezone,
        market_state=info.get("marketState"),
    )
    context = _build_event_context(
        ticker=ticker,
        info=info,
        history=history,
        ex_date=ex_date,
        dividend_amount=dividend_amount,
        costs=costs,
        holding_period_days=holding_period_days,
        timezone=timezone,
    )
    baseline = _calculate_historical_baseline(history, context, ticker)

    cache_key = _generate_cache_key(context, baseline)
    cached_result = await cache.get(cache_key)
    if cached_result is not None:
        if isinstance(cached_result, models_events_dividends.DividendEventAnalysis):
            return cached_result
        if isinstance(cached_result, dict):
            return models_events_dividends.DividendEventAnalysis.model_validate(cached_result)
        raise RuntimeError("Dividend analysis cache contains an invalid value")

    country = conv.country_to_iso2(context.country or "")
    try:
        research = await _research_dividend_event(context, baseline, country=country)
    except DividendEventAIError as exc:
        result = _build_failed_analysis(context, baseline, str(exc))
        await cache.set(cache_key, result, ttl=_FAILED_ANALYSIS_CACHE_TTL)
        return result

    try:
        assessment_result = await _assess_dividend_event(context, baseline, research, country=country)
        result = _build_final_analysis(
            context,
            baseline,
            research,
            assessment_result.assessment,
            validation_warnings=assessment_result.validation_warnings,
        )
    except DividendEventAIError as exc:
        result = _build_failed_analysis(context, baseline, str(exc), research=research)
        await cache.set(cache_key, result, ttl=_FAILED_ANALYSIS_CACHE_TTL)
        return result
    except ValidationError:
        result = _build_failed_analysis(
            context,
            baseline,
            "Dividend assessment failed final validation",
            research=research,
        )
        await cache.set(cache_key, result, ttl=_FAILED_ANALYSIS_CACHE_TTL)
        return result

    await cache.set(cache_key, result, ttl=_cache_ttl(context))
    return result


def _validate_request_values(
    symbol: str,
    ex_date: date,
    dividend_amount: float,
    costs: models_events_dividends.DividendTransactionCosts,
    holding_period_days: int,
) -> None:
    if not symbol.strip():
        raise DividendEventInputError("Symbol is required")
    if len(symbol) > 128:
        raise DividendEventInputError("Symbol must not exceed 128 characters")
    if not isinstance(ex_date, date) or isinstance(ex_date, datetime):
        raise DividendEventInputError("Ex-dividend date must be a date")
    if not math.isfinite(dividend_amount) or dividend_amount <= 0:
        raise DividendEventInputError("Dividend amount must be a positive finite number")
    if not 1 <= holding_period_days <= 365:
        raise DividendEventInputError("Holding period must be between 1 and 365 days")
    transaction_cost_values = (
        costs.dividend_capture_per_share,
        costs.post_dividend_discount_per_share,
    )
    if any(not math.isfinite(cost) or cost < 0 for cost in transaction_cost_values):
        raise DividendEventInputError("Transaction costs must be non-negative finite numbers")


def _resolve_exchange_timezone(info: dict, history: pd.DataFrame) -> ZoneInfo:
    timezone_names: list[str] = []
    if isinstance(history.index, pd.DatetimeIndex) and history.index.tz is not None:
        timezone_names.append(str(history.index.tz))
    timezone_names.extend(
        str(value).strip()
        for value in (
            info.get("exchangeTimezoneName"),
            info.get("timeZoneFullName"),
        )
        if value
    )
    for timezone_name in dict.fromkeys(timezone_names):
        try:
            return ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            continue
    raise DividendEventInsufficientDataError("Ticker metadata does not contain a valid exchange timezone")


def _normalize_history(
    history: pd.DataFrame,
    timezone,
    *,
    market_state: object = None,
) -> pd.DataFrame:
    required_columns = {"Open", "High", "Low", "Close", "Volume", "Dividends"}
    missing_columns = required_columns - set(history.columns)
    if missing_columns:
        raise DividendEventInsufficientDataError(f"Market history is missing columns: {sorted(missing_columns)}")
    if not isinstance(history.index, pd.DatetimeIndex):
        raise DividendEventInsufficientDataError("Market history must use a datetime index")

    normalized = history.copy().sort_index()
    normalized.index = (
        normalized.index.tz_localize(timezone) if normalized.index.tz is None else normalized.index.tz_convert(timezone)
    )
    normalized_market_state = str(market_state or "").strip().upper()
    if (
        not normalized.empty
        and normalized.index[-1].date() == datetime.now(timezone).date()
        and normalized_market_state in {"PRE", "PREPRE", "REGULAR"}
    ):
        normalized = normalized.iloc[:-1].copy()
    if len(normalized) < 90:
        raise DividendEventInsufficientDataError("At least 90 complete market sessions are required")
    return normalized


def _build_event_context(
    *,
    ticker: yf.Ticker,
    info: dict,
    history: pd.DataFrame,
    ex_date: date,
    dividend_amount: float,
    costs: models_events_dividends.DividendTransactionCosts,
    holding_period_days: int,
    timezone,
) -> models_events_dividends.DividendEventContext:
    as_of = datetime.now(UTC)
    today = as_of.astimezone(timezone).date()
    if ex_date > today:
        phase: models_events_dividends.DividendEventPhase = "BeforeExDate"
    elif ex_date == today:
        phase = "ExDate"
    elif ex_date + timedelta(days=holding_period_days) >= today:
        phase = "PostExDate"
    else:
        phase = "Historical"

    reference_price = _reference_price(info, history, ex_date, today)
    asset_type = yfutils.detect_asset_type(ticker) or types.OTHER_ASSET
    if asset_type is None:
        asset_type = types.OTHER_ASSET
    symbol = str(info.get("symbol") or "").strip().upper()
    if not symbol:
        raise DividendEventInputError("Ticker metadata does not contain a symbol")
    exchange = conv.normalize_exchange_code(info.get("fullExchangeName") or info.get("exchange") or "")
    if not exchange:
        raise DividendEventInsufficientDataError("Ticker metadata does not contain an exchange")
    currency = str(info.get("currency") or "").strip().upper()
    if not currency:
        raise DividendEventInsufficientDataError("Ticker metadata does not contain a currency")

    return models_events_dividends.DividendEventContext(
        symbol=symbol,
        exchange=exchange,
        company_name=info.get("longName") or info.get("shortName"),
        currency=currency,
        country=info.get("country"),
        asset_type=asset_type,
        exchange_timezone=str(timezone),
        ex_date=ex_date,
        phase=phase,
        as_of=as_of,
        reference_price=reference_price,
        dividend_amount=dividend_amount,
        gross_dividend_yield=dividend_amount / reference_price,
        holding_period_days=holding_period_days,
        transaction_costs=costs,
    )


def _reference_price(
    info: dict,
    history: pd.DataFrame,
    ex_date: date,
    today: date,
) -> float:
    if ex_date <= today:
        prior_rows = history[history.index.date < ex_date]
        if not prior_rows.empty:
            prior_close = _finite_number(prior_rows.iloc[-1]["Close"])
            if prior_close is not None and prior_close > 0:
                return prior_close

    current_price = _finite_number(info.get("regularMarketPrice"))
    if current_price is None or current_price <= 0:
        current_price = _finite_number(history.iloc[-1]["Close"])
    if current_price is None or current_price <= 0:
        raise DividendEventInsufficientDataError("A positive reference price is required")
    return current_price


def _calculate_historical_baseline(
    history: pd.DataFrame,
    context: models_events_dividends.DividendEventContext,
    ticker: yf.Ticker,
) -> models_events_dividends.DividendHistoricalBaseline:
    timezone = history.index.tz
    today = context.as_of.astimezone(timezone).date()
    sample_cutoff = min(context.ex_date, today) - timedelta(days=context.holding_period_days)
    samples = _extract_dividend_samples(
        history,
        sample_cutoff=sample_cutoff,
        holding_period_days=context.holding_period_days,
        costs=context.transaction_costs,
    )
    if not samples:
        raise DividendEventInsufficientDataError("No complete historical dividend events are available")

    open_drop = _drop_estimate(samples, "open_drop_ratio", context)
    close_drop = _drop_estimate(samples, "close_drop_ratio", context)
    intraday_low_drop = _drop_estimate(samples, "intraday_low_drop_ratio", context)
    drawdown = _drop_estimate(samples, "drawdown_ratio", context)
    capture_target = max(
        0.0,
        context.reference_price - context.dividend_amount + context.transaction_costs.dividend_capture_per_share,
    )
    discount_target = models_events_dividends.DividendNumericRange(
        minimum=max(
            0.0,
            close_drop.estimated_price.minimum + context.transaction_costs.post_dividend_discount_per_share,
        ),
        maximum=max(
            0.0,
            close_drop.estimated_price.maximum + context.transaction_costs.post_dividend_discount_per_share,
        ),
    )

    quality_flags = ["Source history does not classify regular and special distributions."]
    if len(samples) < _MINIMUM_COMPARABLE_EVENTS:
        quality_flags.append(f"Only {len(samples)} comparable historical dividend event(s) were available.")

    return models_events_dividends.DividendHistoricalBaseline(
        sample_count=len(samples),
        sample_quality="Sufficient" if len(samples) >= _MINIMUM_COMPARABLE_EVENTS else "Limited",
        quality_flags=quality_flags,
        ex_date_open_drop=open_drop,
        ex_date_close_drop=close_drop,
        ex_date_intraday_low_drop=intraday_low_drop,
        post_ex_date_drawdown=drawdown,
        pre_ex_close_recovery=_recovery_estimate(
            samples,
            "pre_ex_close_recovery_days",
            models_events_dividends.DividendNumericRange(
                minimum=context.reference_price,
                maximum=context.reference_price,
            ),
            context.ex_date,
        ),
        dividend_capture_break_even_recovery=_recovery_estimate(
            samples,
            "capture_break_even_recovery_days",
            models_events_dividends.DividendNumericRange(minimum=capture_target, maximum=capture_target),
            context.ex_date,
        ),
        post_dividend_discount_break_even_recovery=_recovery_estimate(
            samples,
            "discount_break_even_recovery_days",
            discount_target,
            context.ex_date,
        ),
        technical_context=_technical_context(history, ticker),
    )


def _extract_dividend_samples(
    history: pd.DataFrame,
    *,
    sample_cutoff: date,
    holding_period_days: int,
    costs: models_events_dividends.DividendTransactionCosts,
) -> list[_DividendSample]:
    samples: list[_DividendSample] = []
    for position in range(1, len(history)):
        event_time = history.index[position]
        event_row = history.iloc[position]
        dividend = _finite_number(event_row["Dividends"])
        if dividend is None or dividend <= 0 or event_time.date() > sample_cutoff:
            continue

        previous_close = _finite_number(history.iloc[position - 1]["Close"])
        open_price = _finite_number(event_row["Open"])
        close_price = _finite_number(event_row["Close"])
        low_price = _finite_number(event_row["Low"])
        event_volume = _finite_number(event_row["Volume"])
        if (
            previous_close is None
            or previous_close <= 0
            or open_price is None
            or close_price is None
            or low_price is None
            or event_volume is None
            or event_volume <= 0
        ):
            continue

        window_end = event_time + pd.Timedelta(days=holding_period_days)
        event_window = history.loc[(history.index >= event_time) & (history.index <= window_end)]
        pre_ex_close_recovery_time = _first_recovery_time(
            event_window,
            previous_close,
        )
        drawdown_window = (
            event_window.loc[event_window.index <= pre_ex_close_recovery_time]
            if pre_ex_close_recovery_time is not None
            else event_window
        )
        valid_lows = [
            value for value in (_finite_number(raw_value) for raw_value in drawdown_window["Low"]) if value is not None
        ]
        if not valid_lows:
            continue

        samples.append(
            _DividendSample(
                open_drop_ratio=(previous_close - open_price) / dividend,
                close_drop_ratio=(previous_close - close_price) / dividend,
                intraday_low_drop_ratio=(previous_close - low_price) / dividend,
                drawdown_ratio=(previous_close - min(valid_lows)) / dividend,
                pre_ex_close_recovery_days=_first_recovery_days(
                    event_window,
                    event_time,
                    previous_close,
                ),
                capture_break_even_recovery_days=_first_recovery_days(
                    event_window,
                    event_time,
                    max(0.0, previous_close - dividend + costs.dividend_capture_per_share),
                ),
                discount_break_even_recovery_days=_first_recovery_days(
                    event_window,
                    event_time,
                    close_price + costs.post_dividend_discount_per_share,
                ),
            )
        )
    return samples


def _first_recovery_days(
    window: pd.DataFrame,
    event_time: pd.Timestamp,
    target_price: float,
) -> int | None:
    recovery_time = _first_recovery_time(window, target_price)
    if recovery_time is None:
        return None
    return (recovery_time.date() - event_time.date()).days


def _first_recovery_time(
    window: pd.DataFrame,
    target_price: float,
) -> pd.Timestamp | None:
    for recovery_time, row in window.iterrows():
        close_price = _finite_number(row["Close"])
        volume = _finite_number(row["Volume"])
        if close_price is not None and volume is not None and volume > 0 and close_price >= target_price:
            return recovery_time
    return None


def _drop_estimate(
    samples: list[_DividendSample],
    attribute: str,
    context: models_events_dividends.DividendEventContext,
) -> models_events_dividends.DividendDropEstimate:
    ratios = [getattr(sample, attribute) for sample in samples]
    ratio_range = _numeric_range(ratios)
    raw_minimum = ratio_range.minimum * context.dividend_amount
    raw_maximum = ratio_range.maximum * context.dividend_amount
    amount_range = models_events_dividends.DividendNumericRange(
        minimum=min(raw_minimum, context.reference_price),
        maximum=min(raw_maximum, context.reference_price),
    )
    estimated_prices = sorted(
        (
            max(0.0, context.reference_price - amount_range.maximum),
            max(0.0, context.reference_price - amount_range.minimum),
        )
    )
    return models_events_dividends.DividendDropEstimate(
        drop_amount=amount_range,
        drop_percent=models_events_dividends.DividendNumericRange(
            minimum=amount_range.minimum / context.reference_price,
            maximum=amount_range.maximum / context.reference_price,
        ),
        drop_to_dividend_ratio=models_events_dividends.DividendNumericRange(
            minimum=amount_range.minimum / context.dividend_amount,
            maximum=amount_range.maximum / context.dividend_amount,
        ),
        estimated_price=models_events_dividends.DividendNumericRange(
            minimum=estimated_prices[0],
            maximum=estimated_prices[1],
        ),
    )


def _numeric_range(values: list[float]) -> models_events_dividends.DividendNumericRange:
    finite_values = [value for value in values if math.isfinite(value)]
    if not finite_values:
        raise DividendEventInsufficientDataError("A finite historical range could not be calculated")
    series = pd.Series(finite_values, dtype=float)
    return models_events_dividends.DividendNumericRange(
        minimum=float(series.quantile(0.25)),
        maximum=float(series.quantile(0.75)),
    )


def _recovery_estimate(
    samples: list[_DividendSample],
    attribute: str,
    target_price: models_events_dividends.DividendNumericRange,
    ex_date: date,
) -> models_events_dividends.DividendRecoveryEstimate:
    recovery_days = [getattr(sample, attribute) for sample in samples]
    successful_days = [days for days in recovery_days if days is not None]
    if not successful_days:
        return models_events_dividends.DividendRecoveryEstimate(
            target_price=target_price,
            success_probability=0.0,
            days=None,
            estimated_date_min=None,
            estimated_date_max=None,
        )

    series = pd.Series(successful_days, dtype=float)
    day_range = models_events_dividends.DividendDayRange(
        minimum=max(0, math.floor(float(series.quantile(0.25)))),
        maximum=max(0, math.ceil(float(series.quantile(0.75)))),
    )
    return models_events_dividends.DividendRecoveryEstimate(
        target_price=target_price,
        success_probability=len(successful_days) / len(samples),
        days=day_range,
        estimated_date_min=ex_date + timedelta(days=day_range.minimum),
        estimated_date_max=ex_date + timedelta(days=day_range.maximum),
    )


def _technical_context(
    history: pd.DataFrame,
    ticker: yf.Ticker,
) -> models_events_dividends.DividendTechnicalContext:
    history7d = history.iloc[-7:].copy()
    history7d["DVT"] = (
        (history7d["Open"] + history7d["Close"] + history7d["High"] + history7d["Low"]) / 4 * history7d["Volume"]
    )
    history30d = history.iloc[-30:].copy()
    rsi_series = finhub_utils.calc_rsi(history30d, 14)

    return models_events_dividends.DividendTechnicalContext(
        beta=_finite_number(ticker.info.get("beta")),
        rsi14=_finite_number(rsi_series.iloc[-1]) if not rsi_series.empty else None,
        average_daily_value_traded_7d=_finite_number(history7d["DVT"].mean()),
        average_volume_30d=_finite_number(history30d["Volume"].mean()),
        daily_return_volatility_30d=_non_negative_number(
            history30d["Close"].pct_change(fill_method=None).dropna().std()
        ),
        bid_ask_spread=_non_negative_number(finhub_utils.calc_bid_ask_spread_roll(history30d)),
        stock_trend_60d=(
            _finite_number(finhub_utils.calc_trend_ema(history.iloc[-60:])) if len(history) >= 60 else None
        ),
        market_trend_60d=_comparison_trend(yfutils.lookup_index_yf_static_symbol(ticker=ticker), history.index.tz),
        peer_trend_60d=_comparison_trend(yfutils.lookup_peer_yf_static_symbol(ticker=ticker), history.index.tz),
    )


def _comparison_trend(symbol: str | None, timezone) -> float | None:
    if not symbol:
        return None
    comparison_ticker = yf.Ticker(symbol)
    if not comparison_ticker.info.get("symbol"):
        return None
    comparison_history = comparison_ticker.history(period="61d", interval="1d", auto_adjust=False)
    if comparison_history.empty or len(comparison_history) < 55:
        return None
    if not isinstance(comparison_history.index, pd.DatetimeIndex):
        return None
    comparison_history = comparison_history.copy()
    comparison_history.index = (
        comparison_history.index.tz_localize(timezone)
        if comparison_history.index.tz is None
        else comparison_history.index.tz_convert(timezone)
    )
    return _finite_number(finhub_utils.calc_trend_ema(comparison_history))


def _finite_number(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _non_negative_number(value: object) -> float | None:
    number = _finite_number(value)
    return number if number is not None and number >= 0 else None


async def _research_dividend_event(
    context: models_events_dividends.DividendEventContext,
    baseline: models_events_dividends.DividendHistoricalBaseline,
    *,
    country: str,
) -> _DividendResearch:
    prompt = ai_prompt_utils.render_prompt(
        "dividend_event_research.txt",
        {
            "EVENT_JSON": context.model_dump_json(),
            "BASELINE_JSON": baseline.model_dump_json(),
        },
    )
    try:
        response = await ai_helper.ai_exec_task(
            _RESEARCH_TASK,
            prompt,
            country=country,
            response_json_schema=_DividendResearchDraft.model_json_schema(),
            schema_name=_RESEARCH_SCHEMA_NAME,
        )
    except (OSError, ValueError, openai.APIError) as exc:
        logging.exception("[Dividend Analysis] Research provider call failed.")
        raise DividendEventAIError("Dividend research provider failed") from exc
    if response.is_error:
        logging.error("[Dividend Analysis] Research failed: %s", response.error_msg)
        raise DividendEventAIError("Dividend research failed")

    try:
        raw_research = _DividendResearchResponse.model_validate_json(response.completion)
        repaired_research = _repair_research_references(raw_research)
    except ValidationError as exc:
        raise DividendEventAIError("Dividend research returned an invalid structured response") from exc
    if raw_research.symbol != context.symbol:
        raise DividendEventAIError("Dividend research returned a different symbol")

    try:
        return _finalize_research_references(
            repaired_research,
            response.citation_urls,
            accessed_at=datetime.now(UTC),
        )
    except (TypeError, ValueError, ValidationError) as exc:
        raise DividendEventAIError("Dividend research returned invalid references") from exc


def _repair_research_references(
    research: _DividendResearchResponse,
) -> _DividendResearchDraft:
    research_data = research.model_dump()
    registry_ids = {reference.id for reference in research.references}
    missing_ids: set[str] = set()

    for section_name in _RESEARCH_SECTION_NAMES:
        section = research_data[section_name]
        orphan_ids = set(section["reference_ids"]) - registry_ids
        missing_ids.update(orphan_ids)
        valid_section_ids = [reference_id for reference_id in section["reference_ids"] if reference_id in registry_ids]
        repaired_facts = []
        dropped_facts = 0

        for fact in section["facts"]:
            fact_orphans = set(fact["reference_ids"]) - registry_ids
            missing_ids.update(fact_orphans)
            orphan_ids.update(fact_orphans)
            valid_fact_ids = [reference_id for reference_id in fact["reference_ids"] if reference_id in registry_ids]
            if not valid_fact_ids:
                dropped_facts += 1
                continue
            fact["reference_ids"] = list(dict.fromkeys(valid_fact_ids))
            repaired_facts.append(fact)
            valid_section_ids.extend(valid_fact_ids)

        section["facts"] = repaired_facts
        section["reference_ids"] = list(dict.fromkeys(valid_section_ids))
        if orphan_ids or dropped_facts:
            missing_text = ", ".join(sorted(orphan_ids))
            summary = f"Ignored missing source IDs: {missing_text}."
            if dropped_facts:
                summary += f" Removed {dropped_facts} unsupported fact(s)."
            section["data_gaps"].append(summary)

    used_ids = ai_reference_utils.collect_reference_ids(research_data)
    research_data["references"] = [
        reference for reference in research_data["references"] if reference["id"] in used_ids
    ]
    if missing_ids:
        logging.warning(
            "[Dividend Analysis] Ignored research links to missing source IDs: %s.",
            ", ".join(sorted(missing_ids)),
        )
    return _DividendResearchDraft.model_validate(research_data)


def _finalize_research_references(
    research: _DividendResearchDraft,
    citation_urls: list[str],
    *,
    accessed_at: datetime,
) -> _DividendResearch:
    canonicalized = ai_reference_utils.canonicalize_reference_sources(
        research.references,
        citation_urls,
        accessed_at=accessed_at,
    )
    unverified_count = sum(not reference.is_verified for reference in canonicalized.references)
    if unverified_count:
        logging.warning(
            "[Dividend Analysis] %d of %d research sources could not be provider-verified.",
            unverified_count,
            len(canonicalized.references),
        )

    research_data = ai_reference_utils.remap_reference_ids(research, canonicalized.id_map)
    if not isinstance(research_data, dict):
        raise TypeError("Remapped dividend research must be an object")
    research_data["as_of"] = accessed_at
    research_data["references"] = [reference.model_dump() for reference in canonicalized.references]
    return _DividendResearch.model_validate(research_data)


async def _assess_dividend_event(
    context: models_events_dividends.DividendEventContext,
    baseline: models_events_dividends.DividendHistoricalBaseline,
    research: _DividendResearch,
    *,
    country: str,
) -> _DividendAssessmentResult:
    prompt = ai_prompt_utils.render_prompt(
        "dividend_event_assessment.txt",
        {
            "EVENT_JSON": context.model_dump_json(),
            "BASELINE_JSON": baseline.model_dump_json(),
            "RESEARCH_JSON": research.model_dump_json(),
        },
    )
    try:
        response = await ai_helper.ai_exec_task(
            _ASSESS_TASK,
            prompt,
            country=country,
            response_json_schema=_DividendAssessmentDraft.model_json_schema(),
            schema_name=_ASSESSMENT_SCHEMA_NAME,
        )
    except (OSError, ValueError, openai.APIError) as exc:
        logging.exception("[Dividend Analysis] Assessment provider call failed.")
        raise DividendEventAIError("Dividend assessment provider failed") from exc
    if response.is_error:
        logging.error("[Dividend Analysis] Assessment failed: %s", response.error_msg)
        raise DividendEventAIError("Dividend assessment failed")

    try:
        assessment = _DividendAssessmentDraft.model_validate_json(response.completion)
    except ValidationError as exc:
        raise DividendEventAIError("Dividend assessment returned an invalid structured response") from exc
    if assessment.symbol != context.symbol:
        raise DividendEventAIError("Dividend assessment returned a different symbol")
    if context.phase != "BeforeExDate" and assessment.dividend_capture.eligibility != "Ineligible":
        raise DividendEventAIError("Dividend assessment did not mark capture as ineligible")

    known_reference_ids = {reference.id for reference in research.references}
    unknown_reference_ids = ai_reference_utils.collect_reference_ids(assessment) - known_reference_ids
    if unknown_reference_ids:
        raise DividendEventAIError(f"Dividend assessment used unknown references: {sorted(unknown_reference_ids)}")
    assessment, validation_warnings = _normalize_strategy_profit_loss(context, assessment)
    _validate_assessment_targets(context, baseline, assessment)
    return _DividendAssessmentResult(
        assessment=assessment,
        validation_warnings=tuple(validation_warnings),
    )


def _normalize_strategy_profit_loss(
    context: models_events_dividends.DividendEventContext,
    assessment: _DividendAssessmentDraft,
) -> tuple[_DividendAssessmentDraft, list[str]]:
    assessment_data = assessment.model_dump(mode="python")
    validation_warnings: list[str] = []
    for field_name, strategy in (
        ("dividend_capture", assessment.dividend_capture),
        ("post_dividend_discount", assessment.post_dividend_discount),
    ):
        if strategy.eligibility != "Eligible":
            continue
        expected_profit_loss = _expected_strategy_profit_loss(context, strategy)
        if strategy.expected_profit_loss_per_share is not None and _ranges_close(
            strategy.expected_profit_loss_per_share,
            expected_profit_loss,
            absolute_tolerance=0.02,
        ):
            continue

        warning = (
            f"{strategy.strategy} returned inconsistent profit-and-loss estimates; "
            "the application corrected them from entry, exit, dividend, and transaction costs."
        )
        strategy_data = assessment_data[field_name]
        strategy_data["expected_profit_loss_per_share"] = expected_profit_loss.model_dump()
        existing_data_gaps = [data_gap for data_gap in dict.fromkeys(strategy_data["data_gaps"]) if data_gap != warning]
        strategy_data["data_gaps"] = [
            *existing_data_gaps[:19],
            warning,
        ]
        validation_warnings.append(warning)
        logging.warning("[Dividend Analysis] %s", warning)

    if not validation_warnings:
        return assessment, []
    return _DividendAssessmentDraft.model_validate(assessment_data), validation_warnings


def _validate_assessment_targets(
    context: models_events_dividends.DividendEventContext,
    baseline: models_events_dividends.DividendHistoricalBaseline,
    assessment: _DividendAssessmentDraft,
) -> None:
    if assessment.evidence_adjusted_ex_date_close_drop is not None:
        _validate_assessment_drop(context, assessment.evidence_adjusted_ex_date_close_drop)

    recovery_estimates = (
        assessment.evidence_adjusted_pre_ex_close_recovery,
        assessment.evidence_adjusted_capture_break_even_recovery,
        assessment.evidence_adjusted_discount_break_even_recovery,
    )
    for estimate in recovery_estimates:
        if estimate is not None:
            _validate_assessment_recovery_dates(context, estimate)

    pre_ex_recovery = assessment.evidence_adjusted_pre_ex_close_recovery
    expected_pre_ex_target = models_events_dividends.DividendNumericRange(
        minimum=context.reference_price,
        maximum=context.reference_price,
    )
    if pre_ex_recovery is not None and pre_ex_recovery.target_price != expected_pre_ex_target:
        raise DividendEventAIError("Dividend assessment changed the pre-ex-close recovery target")

    capture = assessment.dividend_capture
    capture_recovery = assessment.evidence_adjusted_capture_break_even_recovery
    capture_target = (
        _capture_break_even_target(context, capture.expected_entry_price)
        if capture.expected_entry_price is not None
        else baseline.dividend_capture_break_even_recovery.target_price
    )
    if capture_recovery is not None and capture_recovery.target_price != capture_target:
        raise DividendEventAIError("Dividend assessment returned an inconsistent capture recovery target")
    if capture.break_even_price is not None and capture.break_even_price != capture_target:
        raise DividendEventAIError("Dividend assessment returned an inconsistent capture break-even price")
    if (
        capture.eligibility == "Eligible"
        and capture_recovery is not None
        and (
            capture.recovery_days != capture_recovery.days
            or not _numbers_close(
                capture.success_probability,
                capture_recovery.success_probability,
            )
        )
    ):
        raise DividendEventAIError("Dividend assessment returned inconsistent capture recovery estimates")
    if capture.eligibility == "Eligible":
        _validate_strategy_profit_loss(context, capture)

    discount = assessment.post_dividend_discount
    discount_recovery = assessment.evidence_adjusted_discount_break_even_recovery
    discount_target = (
        _discount_break_even_target(context, discount.expected_entry_price)
        if discount.expected_entry_price is not None
        else baseline.post_dividend_discount_break_even_recovery.target_price
    )
    if discount_recovery is not None and discount_recovery.target_price != discount_target:
        raise DividendEventAIError("Dividend assessment returned an inconsistent discount recovery target")
    if discount.break_even_price is not None and discount.break_even_price != discount_target:
        raise DividendEventAIError("Dividend assessment returned an inconsistent discount break-even price")
    if (
        discount.eligibility == "Eligible"
        and discount_recovery is not None
        and (
            discount.recovery_days != discount_recovery.days
            or not _numbers_close(
                discount.success_probability,
                discount_recovery.success_probability,
            )
        )
    ):
        raise DividendEventAIError("Dividend assessment returned inconsistent discount recovery estimates")
    if discount.eligibility == "Eligible":
        _validate_strategy_profit_loss(context, discount)


def _validate_assessment_drop(
    context: models_events_dividends.DividendEventContext,
    estimate: models_events_dividends.DividendDropEstimate,
) -> None:
    if estimate.drop_amount.maximum > context.reference_price:
        raise DividendEventAIError("Dividend assessment returned a drop above the reference price")
    expected_percent = models_events_dividends.DividendNumericRange(
        minimum=estimate.drop_amount.minimum / context.reference_price,
        maximum=estimate.drop_amount.maximum / context.reference_price,
    )
    expected_dividend_ratio = models_events_dividends.DividendNumericRange(
        minimum=estimate.drop_amount.minimum / context.dividend_amount,
        maximum=estimate.drop_amount.maximum / context.dividend_amount,
    )
    expected_price = models_events_dividends.DividendNumericRange(
        minimum=context.reference_price - estimate.drop_amount.maximum,
        maximum=context.reference_price - estimate.drop_amount.minimum,
    )
    if not _ranges_close(estimate.drop_percent, expected_percent):
        raise DividendEventAIError("Dividend assessment returned inconsistent drop percentages")
    if not _ranges_close(estimate.drop_to_dividend_ratio, expected_dividend_ratio):
        raise DividendEventAIError("Dividend assessment returned inconsistent dividend-normalized drops")
    if not _ranges_close(estimate.estimated_price, expected_price):
        raise DividendEventAIError("Dividend assessment returned inconsistent ex-date prices")


def _validate_strategy_profit_loss(
    context: models_events_dividends.DividendEventContext,
    assessment: models_events_dividends.DividendStrategyAssessment,
) -> None:
    if (
        assessment.expected_entry_price is None
        or assessment.expected_exit_price is None
        or assessment.expected_profit_loss_per_share is None
    ):
        raise DividendEventAIError("Eligible strategy is missing profit-and-loss estimates")
    expected_profit_loss = _expected_strategy_profit_loss(context, assessment)
    if not _ranges_close(
        assessment.expected_profit_loss_per_share,
        expected_profit_loss,
        absolute_tolerance=0.02,
    ):
        raise DividendEventAIError("Dividend assessment returned inconsistent profit-and-loss estimates")


def _expected_strategy_profit_loss(
    context: models_events_dividends.DividendEventContext,
    assessment: models_events_dividends.DividendStrategyAssessment,
) -> models_events_dividends.DividendNumericRange:
    if assessment.expected_entry_price is None or assessment.expected_exit_price is None:
        raise DividendEventAIError("Eligible strategy is missing entry or exit estimates")
    income = context.dividend_amount if assessment.strategy == "DividendCapture" else 0.0
    cost = (
        context.transaction_costs.dividend_capture_per_share
        if assessment.strategy == "DividendCapture"
        else context.transaction_costs.post_dividend_discount_per_share
    )
    return models_events_dividends.DividendNumericRange(
        minimum=(assessment.expected_exit_price.minimum - assessment.expected_entry_price.maximum + income - cost),
        maximum=(assessment.expected_exit_price.maximum - assessment.expected_entry_price.minimum + income - cost),
    )


def _numbers_close(left: float | None, right: float | None) -> bool:
    if left is None or right is None:
        return left is right
    return math.isclose(left, right, rel_tol=1e-6, abs_tol=1e-6)


def _ranges_close(
    left: models_events_dividends.DividendNumericRange,
    right: models_events_dividends.DividendNumericRange,
    *,
    absolute_tolerance: float = 1e-6,
) -> bool:
    return math.isclose(
        left.minimum,
        right.minimum,
        rel_tol=1e-6,
        abs_tol=absolute_tolerance,
    ) and math.isclose(
        left.maximum,
        right.maximum,
        rel_tol=1e-6,
        abs_tol=absolute_tolerance,
    )


def _validate_assessment_recovery_dates(
    context: models_events_dividends.DividendEventContext,
    estimate: models_events_dividends.DividendRecoveryEstimate,
) -> None:
    if estimate.days is None:
        return
    if estimate.days.maximum > context.holding_period_days:
        raise DividendEventAIError("Dividend assessment recovery exceeds the holding window")
    if estimate.estimated_date_min != context.ex_date + timedelta(
        days=estimate.days.minimum
    ) or estimate.estimated_date_max != context.ex_date + timedelta(days=estimate.days.maximum):
        raise DividendEventAIError("Dividend assessment returned inconsistent recovery dates")


def _capture_break_even_target(
    context: models_events_dividends.DividendEventContext,
    entry_price: models_events_dividends.DividendNumericRange,
) -> models_events_dividends.DividendNumericRange:
    cost = context.transaction_costs.dividend_capture_per_share
    return models_events_dividends.DividendNumericRange(
        minimum=max(0.0, entry_price.minimum - context.dividend_amount + cost),
        maximum=max(0.0, entry_price.maximum - context.dividend_amount + cost),
    )


def _discount_break_even_target(
    context: models_events_dividends.DividendEventContext,
    entry_price: models_events_dividends.DividendNumericRange,
) -> models_events_dividends.DividendNumericRange:
    cost = context.transaction_costs.post_dividend_discount_per_share
    return models_events_dividends.DividendNumericRange(
        minimum=entry_price.minimum + cost,
        maximum=entry_price.maximum + cost,
    )


def _build_final_analysis(
    context: models_events_dividends.DividendEventContext,
    baseline: models_events_dividends.DividendHistoricalBaseline,
    research: _DividendResearch,
    assessment: _DividendAssessmentDraft,
    *,
    validation_warnings: tuple[str, ...] = (),
) -> models_events_dividends.DividendEventAnalysis:
    overall_data_quality = _adjust_data_quality(
        assessment.overall_data_quality,
        baseline.sample_count,
        research.references,
    )
    recommendation = _resolve_recommendation(
        context,
        baseline,
        assessment,
        overall_data_quality=overall_data_quality,
    )
    public_research = models_events_dividends.DividendResearch(
        dividend_terms=_assessment_section(research.dividend_terms),
        issuer_outlook=_assessment_section(research.issuer_outlook),
        event_risks=_assessment_section(research.event_risks),
        market_context=_assessment_section(research.market_context),
    )
    dividend_capture = _add_required_assumptions(assessment.dividend_capture, context)
    post_dividend_discount = _add_required_assumptions(assessment.post_dividend_discount, context)
    return models_events_dividends.DividendEventAnalysis(
        as_of=datetime.now(UTC),
        analysis_status="CompleteWithWarnings" if validation_warnings else "Complete",
        failure_reason=None,
        overall_data_quality=overall_data_quality,
        event=context,
        historical_baseline=baseline,
        research=public_research,
        evidence_adjusted_ex_date_close_drop=assessment.evidence_adjusted_ex_date_close_drop,
        evidence_adjusted_pre_ex_close_recovery=assessment.evidence_adjusted_pre_ex_close_recovery,
        evidence_adjusted_capture_break_even_recovery=assessment.evidence_adjusted_capture_break_even_recovery,
        evidence_adjusted_discount_break_even_recovery=assessment.evidence_adjusted_discount_break_even_recovery,
        dividend_capture=dividend_capture,
        post_dividend_discount=post_dividend_discount,
        recommendation=recommendation,
        validation_warnings=list(validation_warnings),
        references=research.references,
    )


def _build_failed_analysis(
    context: models_events_dividends.DividendEventContext,
    baseline: models_events_dividends.DividendHistoricalBaseline,
    failure_reason: str,
    *,
    research: _DividendResearch | None = None,
) -> models_events_dividends.DividendEventAnalysis:
    public_research = (
        models_events_dividends.DividendResearch(
            dividend_terms=_assessment_section(research.dividend_terms),
            issuer_outlook=_assessment_section(research.issuer_outlook),
            event_risks=_assessment_section(research.event_risks),
            market_context=_assessment_section(research.market_context),
        )
        if research is not None
        else None
    )
    return models_events_dividends.DividendEventAnalysis(
        as_of=datetime.now(UTC),
        analysis_status="Failed",
        failure_reason=failure_reason,
        overall_data_quality="Insufficient",
        event=context,
        historical_baseline=baseline,
        research=public_research,
        evidence_adjusted_ex_date_close_drop=None,
        evidence_adjusted_pre_ex_close_recovery=None,
        evidence_adjusted_capture_break_even_recovery=None,
        evidence_adjusted_discount_break_even_recovery=None,
        dividend_capture=None,
        post_dividend_discount=None,
        recommendation=None,
        validation_warnings=[],
        references=research.references if research is not None else [],
    )


def _assessment_section(
    section: _DividendResearchSection,
) -> models_events_dividends.DividendEvidenceSection:
    return models_events_dividends.DividendEvidenceSection.model_validate(section.model_dump())


def _add_required_assumptions(
    assessment: models_events_dividends.DividendStrategyAssessment,
    context: models_events_dividends.DividendEventContext,
) -> models_events_dividends.DividendStrategyAssessment:
    assumptions = [
        *assessment.assumptions,
        "Estimates are gross and pre-tax.",
        f"Analysis uses a {context.holding_period_days}-calendar-day holding window.",
    ]
    if assessment.strategy == "DividendCapture" and context.transaction_costs.dividend_capture_per_share == 0:
        assumptions.append("Assumed zero round-trip transaction cost for dividend capture.")
    if (
        assessment.strategy == "PostDividendDiscount"
        and context.transaction_costs.post_dividend_discount_per_share == 0
    ):
        assumptions.append("Assumed zero round-trip transaction cost for the post-dividend discount.")
    assessment_data = assessment.model_dump()
    assessment_data["assumptions"] = list(dict.fromkeys(assumptions))
    return models_events_dividends.DividendStrategyAssessment.model_validate(assessment_data)


def _adjust_data_quality(
    assessment_quality: types.DataQuality,
    sample_count: int,
    references: list[models_ai.ReferenceSource],
) -> types.DataQuality:
    if sample_count < _MINIMUM_COMPARABLE_EVENTS:
        return "Insufficient"
    verified_count = sum(reference.is_verified for reference in references)
    if verified_count == 0:
        return "Insufficient" if assessment_quality == "Insufficient" else "Low"
    if verified_count < len(references) and assessment_quality == "High":
        return "Medium"
    return assessment_quality


def _resolve_recommendation(
    context: models_events_dividends.DividendEventContext,
    baseline: models_events_dividends.DividendHistoricalBaseline,
    assessment: _DividendAssessmentDraft,
    *,
    overall_data_quality: types.DataQuality,
) -> models_events_dividends.DividendRecommendation:
    capture = assessment.dividend_capture
    discount = assessment.post_dividend_discount
    evidence_estimates = (
        assessment.evidence_adjusted_ex_date_close_drop,
        assessment.evidence_adjusted_pre_ex_close_recovery,
        assessment.evidence_adjusted_capture_break_even_recovery,
        assessment.evidence_adjusted_discount_break_even_recovery,
    )
    if (
        baseline.sample_count < _MINIMUM_COMPARABLE_EVENTS
        or overall_data_quality == "Insufficient"
        or any(estimate is None for estimate in evidence_estimates)
    ):
        outcome: models_events_dividends.DividendRecommendationOutcome = "InsufficientInsights"
        rationale = f"Insufficient validated evidence for a recommendation. {assessment.comparison_rationale}"
    else:
        outcome, rationale = _resolve_eligible_strategy_recommendation(
            context,
            capture,
            discount,
            assessment.comparison_rationale,
        )

    capture_probability = capture.success_probability
    discount_probability = discount.success_probability
    probability_advantage = (
        abs(capture_probability - discount_probability)
        if capture_probability is not None and discount_probability is not None
        else None
    )

    return models_events_dividends.DividendRecommendation(
        outcome=outcome,
        probability_advantage=probability_advantage,
        rationale=rationale,
        reference_ids=list(dict.fromkeys(assessment.comparison_reference_ids)),
    )


def _resolve_eligible_strategy_recommendation(
    context: models_events_dividends.DividendEventContext,
    capture: models_events_dividends.DividendStrategyAssessment,
    discount: models_events_dividends.DividendStrategyAssessment,
    comparison_rationale: str,
) -> tuple[models_events_dividends.DividendRecommendationOutcome, str]:
    if context.phase != "BeforeExDate":
        if discount.eligibility == "InsufficientData" or (
            discount.eligibility == "Eligible"
            and (discount.success_probability is None or discount.confidence < _MINIMUM_RECOMMENDATION_CONFIDENCE)
        ):
            return (
                "InsufficientInsights",
                f"Post-dividend-discount evidence does not pass the minimum gates. {comparison_rationale}",
            )
        if _strategy_is_viable(discount):
            return "PostDividendDiscount", comparison_rationale
        return (
            "NoClearWinner",
            f"No currently eligible strategy has a defensible positive advantage. {comparison_rationale}",
        )

    if capture.eligibility == "InsufficientData" or discount.eligibility == "InsufficientData":
        return (
            "InsufficientInsights",
            f"At least one strategy lacks required estimates. {comparison_rationale}",
        )
    if capture.eligibility != "Eligible" or discount.eligibility != "Eligible":
        return (
            "NoClearWinner",
            f"Both strategies must be eligible for a pre-event comparison. {comparison_rationale}",
        )
    if (
        capture.success_probability is None
        or discount.success_probability is None
        or capture.confidence < _MINIMUM_RECOMMENDATION_CONFIDENCE
        or discount.confidence < _MINIMUM_RECOMMENDATION_CONFIDENCE
    ):
        return (
            "InsufficientInsights",
            f"The strategy estimates do not pass the minimum confidence gates. {comparison_rationale}",
        )

    probability_advantage = abs(capture.success_probability - discount.success_probability)
    if probability_advantage < _MINIMUM_PROBABILITY_ADVANTAGE:
        return (
            "NoClearWinner",
            f"The strategies do not have a clear probability advantage. {comparison_rationale}",
        )

    if capture.success_probability > discount.success_probability and _strategy_is_viable(capture):
        return "DividendCapture", comparison_rationale
    if discount.success_probability > capture.success_probability and _strategy_is_viable(discount):
        return "PostDividendDiscount", comparison_rationale
    return (
        "NoClearWinner",
        f"The higher-probability strategy does not have positive expected net P&L. {comparison_rationale}",
    )


def _strategy_is_viable(
    assessment: models_events_dividends.DividendStrategyAssessment,
) -> bool:
    if (
        assessment.eligibility != "Eligible"
        or assessment.success_probability is None
        or assessment.confidence < _MINIMUM_RECOMMENDATION_CONFIDENCE
        or assessment.expected_profit_loss_per_share is None
    ):
        return False
    expected_midpoint = (
        assessment.expected_profit_loss_per_share.minimum + assessment.expected_profit_loss_per_share.maximum
    ) / 2
    return expected_midpoint > 0


def _generate_cache_key(
    context: models_events_dividends.DividendEventContext,
    baseline: models_events_dividends.DividendHistoricalBaseline,
) -> str:
    context_data = context.model_dump(mode="json", exclude={"as_of"})
    local_as_of_date = context.as_of.astimezone(ZoneInfo(context.exchange_timezone)).date()
    return cache.generate_key(
        _ANALYSIS_CACHE_NAMESPACE,
        _ANALYSIS_PROMPT_VERSION,
        json.dumps(context_data, sort_keys=True),
        baseline.model_dump_json(),
        local_as_of_date.isoformat(),
        _task_cache_identity(_RESEARCH_TASK),
        _task_cache_identity(_ASSESS_TASK),
    )


def _task_cache_identity(task_id: str) -> str:
    task_config = config.settings_llm_task.tasks.get(task_id)
    if task_config is None:
        return task_id
    return json.dumps(
        {
            "task": task_id,
            "vendor": task_config.vendor,
            "tier": task_config.tier,
            "model": task_config.model,
            "reasoning_effort": task_config.reasoning_effort,
            "use_web_search": task_config.use_web_search,
        },
        sort_keys=True,
    )


def _cache_ttl(context: models_events_dividends.DividendEventContext) -> int:
    if context.phase == "ExDate":
        return 60 * 60
    if context.phase == "BeforeExDate":
        local_as_of_date = context.as_of.astimezone(ZoneInfo(context.exchange_timezone)).date()
        days_until_event = (context.ex_date - local_as_of_date).days
        if days_until_event <= 1:
            return 60 * 60
        if days_until_event <= 7:
            return 6 * 60 * 60
        return 24 * 60 * 60
    if context.phase == "PostExDate":
        return 6 * 60 * 60
    return 72 * 60 * 60
