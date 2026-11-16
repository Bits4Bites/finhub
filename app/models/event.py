from __future__ import annotations

import datetime
import json
import re
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from ..utils import json as json_utils

if TYPE_CHECKING:
    pass


_DIVIDEND_EVENT_FIELDS = {
    "sym": "symbol",
    "exchange": "exchange",
    "corp": "company_name",
    "date": "timestamp_str",
    "pdate": "payment_date",
    "cat": "event_category",
    "src": "source_name",
    "link": "link",
    "status": "status",
    "amount": "amount",
    "yield": "dividend_yield",
    "currency": "currency",
}
_EARNINGS_EVENT_FIELDS = {
    "sym": "symbol",
    "exchange": "exchange",
    "corp": "company_name",
    "date": "timestamp_str",
    "src": "source_name",
    "link": "link",
    "report_period": "report_period",
    "status": "status",
}


def _parse_event_records(json_str: str) -> list[dict[str, Any]]:
    events = json.loads(json_utils.normalize_json_str(json_str))
    if not isinstance(events, list):
        raise ValueError("event JSON must contain an array")
    for index, event in enumerate(events):
        if not isinstance(event, dict):
            raise TypeError(f"event at index {index} must be a JSON object")
    return events


def _event_values(
    event: dict[str, Any],
    default_vals: dict[str, Any],
    source_fields: dict[str, str],
) -> dict[str, Any]:
    return {
        model_field: event[source_field] if source_field in event else default_vals[source_field]
        for source_field, model_field in source_fields.items()
        if source_field in event or source_field in default_vals
    }


def _event_date_timestamp(date_str: str) -> int:
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", date_str) is None:
        raise ValueError("event date must use exact YYYY-MM-DD format")
    return int(datetime.datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=datetime.UTC).timestamp())


class EventBase(BaseModel):
    """Common identity, timing, and provenance fields for market events."""

    symbol: str = Field(description="Security symbol associated with the event.")
    exchange: str = Field(
        default="",
        description="Exchange code associated with the security, when available.",
    )
    company_name: str = Field(
        default="",
        description="Company or issuer name, when available.",
    )
    timestamp: int = Field(
        default=0,
        description="Unix timestamp in seconds representing the event date or time.",
    )
    timestamp_str: str = Field(
        description="Human-readable string representation of the event timestamp.",
    )
    event_category: str | None = Field(
        default=None,
        description="Category identifying the type of market event.",
    )
    source_name: str | None = Field(
        default=None,
        description="Name of the source that reported the event.",
    )
    link: str | None = Field(
        default=None,
        description="Source URL containing additional event details.",
    )


class DividendEventAnalysis(EventBase):
    """Legacy dividend-event metrics and AI assessment attached to an event."""

    # ===== base info
    # overview: SymbolOverview = None
    price: float = Field(default=0.0, description="Current security price.")
    # ex_div_date: str | None = None
    # ex_div_date_timestamp: int = 0
    div_amount: float = Field(default=0.0, description="Dividend amount per share.")
    div_yield: float = Field(
        default=0.0,
        description="Dividend amount divided by the current price.",
    )
    # ====== analysis result
    num_samples: int = Field(
        default=0,
        description="Number of historical dividend events used for analysis.",
    )
    drop_price_min: float = Field(
        default=0.0,
        description="Lower historical estimate of the ex-dividend price drop.",
    )
    drop_price_max: float = Field(
        default=0.0,
        description="Upper historical estimate of the ex-dividend price drop.",
    )
    recovery_probability: float = Field(
        default=0.0,
        description="Estimated probability of recovering the reference price.",
    )
    recovery_days_min: int = Field(
        default=0,
        description="Lower estimate of calendar days to price recovery.",
    )
    recovery_days_max: int = Field(
        default=0,
        description="Upper estimate of calendar days to price recovery.",
    )
    recovery_price_min: float = Field(
        default=0.0,
        description="Lower price estimate for recovery.",
    )
    recovery_price_max: float = Field(
        default=0.0,
        description="Upper price estimate for recovery.",
    )
    # ===== technical data, used for further analysis with AI
    beta: float = Field(default=0.0, description="Security beta used as market-sensitivity context.")
    rsi14: int = Field(default=0, description="Fourteen-period relative strength index.")
    avg_dvt_7d: int = Field(
        default=0,
        description="Average daily value traded over seven trading days.",
    )
    std_dvt_7d: int = Field(
        default=0,
        description="Standard deviation of daily value traded over seven trading days.",
    )
    avg_volume_30d: int = Field(
        default=0,
        description="Average daily volume over 30 trading days.",
    )
    std_volume_30d: int = Field(
        default=0,
        description="Standard deviation of daily volume over 30 trading days.",
    )
    bid_ask_spread: float = Field(default=0.0, description="Observed bid-ask spread.")
    trend_60d: float = Field(
        default=0.0,
        description="Security price trend over 60 trading days.",
    )
    market_trend_60d: float = Field(
        default=0.0,
        description="Relevant market trend over 60 trading days.",
    )
    peer_trend_60d: float = Field(
        default=0.0,
        description="Relevant peer-group trend over 60 trading days.",
    )


class UpcomingDividendEvent(EventBase):
    """An announced upcoming dividend or distribution event."""

    status: str = Field(default="", description="Source-reported event status.")
    amount: float = Field(default=0.0, description="Announced dividend amount per share.")
    dividend_yield: float = Field(
        default=0.0,
        description="Announced or derived dividend yield.",
    )
    currency: str = Field(default="", description="Currency of the dividend amount.")
    payment_date: str | None = Field(description="Scheduled payment date, when available.")
    analysis: DividendEventAnalysis | None = Field(
        default=None,
        description="Optional legacy analysis associated with the dividend event.",
    )


def parse_upcoming_dividend_events_from_json(
    json_str: str,
    default_vals: dict[str, Any] | None = None,
) -> list[UpcomingDividendEvent]:
    """Build validated upcoming dividend events from source JSON.

    Args:
        json_str: A JSON array of event objects, optionally wrapped in a complete
            Markdown ``json`` fence. Objects use ``sym``, ``exchange``, ``corp``,
            ``date``, ``pdate``, ``cat``, ``src``, ``link``, ``status``,
            ``amount``, ``yield``, and ``currency`` source keys. ``date`` must
            use exactly ``YYYY-MM-DD``, including a zero-padded month and day.
        default_vals: Optional fallback values keyed by the same source names.
            A fallback applies only when its key is absent; an explicit JSON
            null is retained for final model validation.

    Returns:
        Events in input order, with parser-produced timestamps at midnight UTC
        on their source dates. An empty array returns an empty list. Missing
        values use model defaults where available, and a missing ``cat`` without
        a supplied fallback becomes ``"dividend"``.

    Raises:
        json.JSONDecodeError: If ``json_str`` is not valid JSON.
        ValueError: If the top-level JSON value is not an array, or a date is
            not a valid calendar date in exact ``YYYY-MM-DD`` form.
        TypeError: If an array item is not a JSON object.
        pydantic.ValidationError: If a record or explicit null does not satisfy
            the final event model.
    """
    defaults = default_vals or {}
    events = _parse_event_records(json_str)
    result = []
    for item in events:
        event_values = _event_values(item, defaults, _DIVIDEND_EVENT_FIELDS)
        event_values.setdefault("event_category", "dividend")
        event = UpcomingDividendEvent(**event_values)
        event.timestamp = _event_date_timestamp(event.timestamp_str)
        result.append(event)

    return result


class UpcomingEarningsEvent(EventBase):
    """An announced upcoming earnings-report event."""

    report_period: str | None = Field(
        default=None,
        description="Financial reporting period covered by the announcement.",
    )
    status: str | None = Field(
        default=None,
        description="Source-reported event status.",
    )


def parse_upcoming_earnings_events_from_json(
    json_str: str,
    default_vals: dict[str, Any] | None = None,
) -> list[UpcomingEarningsEvent]:
    """Build validated upcoming earnings events from source JSON.

    Args:
        json_str: A JSON array of event objects, optionally wrapped in a complete
            Markdown ``json`` fence. Objects use ``sym``, ``exchange``, ``corp``,
            ``date``, ``src``, ``link``, ``report_period``, and ``status`` source
            keys. ``date`` must use exactly ``YYYY-MM-DD``, including a
            zero-padded month and day.
        default_vals: Optional fallback values keyed by the same source names.
            A fallback applies only when its key is absent; an explicit JSON
            null is retained for final model validation.

    Returns:
        Events in input order, with the ``earnings`` category and parser-produced
        timestamps at midnight UTC on their source dates. An empty array returns
        an empty list, and missing values use model defaults where available.

    Raises:
        json.JSONDecodeError: If ``json_str`` is not valid JSON.
        ValueError: If the top-level JSON value is not an array, or a date is
            not a valid calendar date in exact ``YYYY-MM-DD`` form.
        TypeError: If an array item is not a JSON object.
        pydantic.ValidationError: If a record or explicit null does not satisfy
            the final event model.
    """
    defaults = default_vals or {}
    events = _parse_event_records(json_str)
    result = []
    for item in events:
        event_values = _event_values(item, defaults, _EARNINGS_EVENT_FIELDS)
        event_values["event_category"] = "earnings"
        event = UpcomingEarningsEvent(**event_values)
        event.timestamp = _event_date_timestamp(event.timestamp_str)
        result.append(event)

    return result
