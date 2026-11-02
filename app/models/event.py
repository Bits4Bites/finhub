from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from ..utils import json as json_utils

if TYPE_CHECKING:
    pass


class EventBase(BaseModel):
    """Common identity, timing, and provenance fields for market events."""

    symbol: str = Field(description="Security symbol associated with the event.")
    exchange: str | None = Field(
        default=None,
        description="Exchange code associated with the security, when available.",
    )
    company_name: str | None = Field(
        default=None,
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
    json_str: str, default_vals: dict[str, Any] = None
) -> list[UpcomingDividendEvent]:
    default_vals = default_vals or {}
    json_str = json_utils.normalize_json_str(json_str)
    events = json.loads(json_str)
    result = []
    for item in events:
        event = UpcomingDividendEvent(
            symbol=item.get("sym", default_vals.get("sym")),
            exchange=item.get("exchange", default_vals.get("exchange")),
            company_name=item.get("corp", default_vals.get("corp")),
            timestamp_str=item.get("date", default_vals.get("date")),
            payment_date=item.get("pdate", default_vals.get("pdate")),
            event_category=item.get("cat", default_vals.get("cat", "Dividend")),
            source_name=item.get("src", default_vals.get("src")),
            link=item.get("link", default_vals.get("link")),
            status=item.get("status", default_vals.get("status")),
            amount=item.get("amount", default_vals.get("amount", 0.0)),
            dividend_yield=item.get("yield", default_vals.get("yield", 0.0)),
            currency=item.get("currency", default_vals.get("currency", "")),
        )
        event.timestamp = int(datetime.strptime(event.timestamp_str or "", "%Y-%m-%d").timestamp())
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
    json_str: str, default_vals: dict[str, Any] = None
) -> list[UpcomingEarningsEvent]:
    default_vals = default_vals or {}
    json_str = json_utils.normalize_json_str(json_str)
    events = json.loads(json_str)
    result = []
    for item in events:
        event = UpcomingEarningsEvent(
            symbol=item.get("sym", default_vals.get("sym")),
            exchange=item.get("exchange", default_vals.get("exchange")),
            company_name=item.get("corp", default_vals.get("corp")),
            timestamp_str=item.get("date", default_vals.get("date")),
            event_category="earnings",
            source_name=item.get("src", default_vals.get("src")),
            link=item.get("link", default_vals.get("link")),
            report_period=item.get("report_period", default_vals.get("report_period")),
            status=item.get("status", default_vals.get("status")),
        )
        event.timestamp = int(datetime.strptime(event.timestamp_str or "", "%Y-%m-%d").timestamp())
        result.append(event)

    return result
