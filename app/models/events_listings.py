from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from ..utils import json as json_utils
from . import event


class ListingOutlook(BaseModel):
    direction: str | None = None
    reason: str | None = None
    confidence: int = 0


class ListingAnalysis(BaseModel):
    status: str | None = None
    data_quality: str | None = None
    search_findings: str | None = None
    stance: str | None = None
    catalyst: str | None = None
    risks: list[str] | None = None
    outlook: dict[str, ListingOutlook] | None = None


def parse_listing_analysis_from_json(json_str: str, default_vals: dict[str, Any] = None) -> dict[str, ListingAnalysis]:
    default_vals = default_vals or {}
    json_str = json_utils.normalize_json_str(json_str)
    analysis = json.loads(json_str)
    result = {}
    for k, v in analysis.items():
        result[k] = ListingAnalysis(
            status=v.get("status", default_vals.get("status")),
            data_quality=v.get("data_quality", default_vals.get("data_quality")),
            search_findings=v.get("search_findings", default_vals.get("search_findings")),
            stance=v.get("stance", default_vals.get("stance")),
            catalyst=v.get("catalyst", default_vals.get("catalyst")),
            risks=v.get("risks", default_vals.get("risks")),
        )
        if "outlook" in v:
            result[k].outlook = {}
            for period in ("d1", "w1", "w2", "m1"):
                if period in v["outlook"]:
                    result[k].outlook[period] = ListingOutlook(
                        direction=v["outlook"][period].get("dir"),
                        reason=v["outlook"][period].get("reason"),
                        confidence=v["outlook"][period].get("confidence"),
                    )

    return result


class ListingEvent(event.EventBase):
    sector: str | None = None
    industry: str | None = None
    principal_activities: str | None = None
    price: float = 0.0
    currency: str = ""
    capital: int = 0
    public_offer_close_date: str | None = None
    analysis: ListingAnalysis | None = None


def parse_new_listing_events_from_json(json_str: str, default_vals: dict[str, Any] = None) -> list[ListingEvent]:
    default_vals = default_vals or {}
    json_str = json_utils.normalize_json_str(json_str)
    events = json.loads(json_str)
    result = []
    for item in events:
        event_obj = ListingEvent(
            symbol=item.get("symbol", default_vals.get("symbol")),
            exchange=item.get("exchange", default_vals.get("exchange")),
            company_name=item.get("company", default_vals.get("company")),
            date=item.get("date", default_vals.get("date")),
            event_category="listing",
            source_name=item.get("src", default_vals.get("src")),
            link=item.get("link", default_vals.get("link")),
            sector=item.get("sector", default_vals.get("sector")),
            principal_activities=item.get("principal_activities", default_vals.get("principal_activities")),
            price=item.get("price", default_vals.get("price", 0.0)),
            currency=item.get("currency", default_vals.get("currency", "")),
            capital=int(item.get("capital", default_vals.get("capital", 0))),
            public_offer_close_date=item.get("public_offer_close_date", default_vals.get("public_offer_close_date")),
        )
        event_obj.timestamp = int(datetime.strptime(event_obj.date or "", "%Y-%m-%d").timestamp())
        result.append(event_obj)

    return result
