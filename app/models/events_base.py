from __future__ import annotations

import datetime
import json
import re
import typing

import pydantic

from ..utils import json as json_utils


class EventBase(pydantic.BaseModel):
    """Common identity, timing, and provenance fields for market events."""

    symbol: str = pydantic.Field(description="Security symbol associated with the event.")
    exchange: str = pydantic.Field(
        default="",
        description="Exchange code associated with the security, when available.",
    )
    company_name: str = pydantic.Field(
        default="",
        description="Company or issuer name, when available.",
    )
    timestamp: int = pydantic.Field(
        default=0,
        description="Unix timestamp in seconds representing the event date or time.",
    )
    timestamp_str: str = pydantic.Field(
        description="Human-readable string representation of the event timestamp.",
    )
    event_category: str | None = pydantic.Field(
        default=None,
        description="Category identifying the type of market event.",
    )
    source_name: str | None = pydantic.Field(
        default=None,
        description="Name of the source that reported the event.",
    )
    link: str | None = pydantic.Field(
        default=None,
        description="Source URL containing additional event details.",
    )


def _parse_event_records(json_str: str) -> list[dict[str, typing.Any]]:
    events = json.loads(json_utils.normalize_json_str(json_str))
    if not isinstance(events, list):
        raise ValueError("event JSON must contain an array")
    for index, event in enumerate(events):
        if not isinstance(event, dict):
            raise TypeError(f"event at index {index} must be a JSON object")
    return events


def _event_values(
    event: dict[str, typing.Any],
    default_vals: dict[str, typing.Any],
    source_fields: dict[str, str],
) -> dict[str, typing.Any]:
    return {
        model_field: event[source_field] if source_field in event else default_vals[source_field]
        for source_field, model_field in source_fields.items()
        if source_field in event or source_field in default_vals
    }


def _event_date_timestamp(date_str: str) -> int:
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", date_str) is None:
        raise ValueError("event date must use exact YYYY-MM-DD format")
    return int(datetime.datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=datetime.UTC).timestamp())
