from __future__ import annotations

import typing

import pydantic

from . import events_base

_EARNINGS_EVENT_FIELDS = {
    "sym": "symbol",
    "exchange": "exchange",
    "corp": "company_name",
    "date": "timestamp_str",
    "src": "source_name",
    "link": "link",
    "report_period": "report_period",
    "status": "status",
    "market_cap": "market_cap",
    "eps": "eps",
    "eps_forecast": "eps_forecast",
    "revenue": "revenue",
    "revenue_forecast": "revenue_forecast",
    "currency": "currency",
}


class UpcomingEarningsEvent(events_base.EventBase):
    """An upcoming earnings announcement with actual and forecast financials.

    Missing numeric values use zero, which does not distinguish unavailable
    data from an actual zero. Market capitalization and revenue use whole
    currency units; earnings per share retain fractional and negative values.
    """

    report_period: str | None = pydantic.Field(
        default=None,
        description="Financial reporting period covered by the announcement.",
    )
    status: str | None = pydantic.Field(
        default=None,
        description="Source-reported event status.",
    )
    market_cap: int = pydantic.Field(
        default=0,
        description="Company market capitalization in whole currency units; zero when unavailable.",
    )
    eps: float = pydantic.Field(
        default=0.0,
        allow_inf_nan=False,
        description="Reported earnings per share in the stated currency; may be negative, or zero when unavailable.",
    )
    eps_forecast: float = pydantic.Field(
        default=0.0,
        allow_inf_nan=False,
        description="Forecast earnings per share in the stated currency; may be negative, or zero when unavailable.",
    )
    revenue: int = pydantic.Field(
        default=0,
        description="Reported revenue in whole currency units; zero when unavailable.",
    )
    revenue_forecast: int = pydantic.Field(
        default=0,
        description="Forecast revenue in whole currency units; zero when unavailable.",
    )
    currency: str = pydantic.Field(
        default="",
        description="Currency code for market capitalization, earnings per share, and revenue.",
    )


def parse_upcoming_earnings_events_from_json(
    json_str: str,
    default_vals: dict[str, typing.Any] | None = None,
) -> list[UpcomingEarningsEvent]:
    """Build validated upcoming earnings events from source JSON.

    Args:
        json_str: A JSON array of event objects, optionally wrapped in a complete
            Markdown ``json`` fence. Objects use ``sym``, ``exchange``, ``corp``,
            ``date``, ``src``, ``link``, ``report_period``, ``status``,
            ``market_cap``, ``eps``, ``eps_forecast``, ``revenue``,
            ``revenue_forecast``, and ``currency`` source keys. ``date`` must
            use exactly ``YYYY-MM-DD``, including a zero-padded month and day.
        default_vals: Optional fallback values keyed by the same source names.
            A fallback applies only when its key is absent; an explicit JSON
            null is retained for final model validation.

    Returns:
        Events in input order, with the ``earnings`` category and parser-produced
        timestamps at midnight UTC on their source dates. An empty array returns
        an empty list. Missing financial amounts use zero unless a fallback is
        supplied; other missing values use model defaults where available.

    Raises:
        json.JSONDecodeError: If ``json_str`` is not valid JSON.
        ValueError: If the top-level JSON value is not an array, or a date is
            not a valid calendar date in exact ``YYYY-MM-DD`` form.
        TypeError: If an array item is not a JSON object.
        pydantic.ValidationError: If a record or explicit null does not satisfy
            the final event model.
    """
    defaults = default_vals or {}
    events = events_base._parse_event_records(json_str)
    result = []
    for item in events:
        event_values = events_base._event_values(item, defaults, _EARNINGS_EVENT_FIELDS)
        event_values["event_category"] = "earnings"
        event = UpcomingEarningsEvent(**event_values)
        event.timestamp = events_base._event_date_timestamp(event.timestamp_str)
        result.append(event)

    return result
