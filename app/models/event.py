from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from ..utils import json as json_utils

if TYPE_CHECKING:
    pass


class EventBase(BaseModel):
    symbol: str
    exchange: str | None = None
    company_name: str | None = None
    timestamp: int = 0
    date: str | None = None
    event_category: str | None = None
    source_name: str | None = None
    link: str | None = None


class DividendEventAnalysis(EventBase):
    # ===== base info
    # overview: SymbolOverview = None
    price: float = 0.0  # current stock price
    # ex_div_date: str | None = None
    # ex_div_date_timestamp: int = 0
    div_amount: float = 0.0
    div_yield: float = 0.0  # div_amount / price
    # ====== analysis result
    num_samples: int = 0  # number of historical dividend events used for analysis
    drop_price_min: float = 0.0
    drop_price_max: float = 0.0
    recovery_probability: float = 0.0
    recovery_days_min: int = 0
    recovery_days_max: int = 0
    recovery_price_min: float = 0.0
    recovery_price_max: float = 0.0
    # ===== technical data, used for further analysis with AI
    beta: float = 0.0
    rsi14: int = 0
    avg_dvt_7d: int = 0
    std_dvt_7d: int = 0
    avg_volume_30d: int = 0
    std_volume_30d: int = 0
    bid_ask_spread: float = 0.0
    trend_60d: float = 0.0
    market_trend_60d: float = 0.0
    peer_trend_60d: float = 0.0
    # ====== analysis result from AI
    llm_error: bool = False
    llm_error_msg: str | None = None
    # llm_response: str | None = None
    search_summary: str | None = None
    strategy: str | None = None
    reasoning: str | None = None
    sentiment_score: float = 0.0
    recovery_probability_adj: float = 0.0
    recovery_days_adj: str | None = None
    drop_price_adj: str | None = None
    recovery_price_adj: str | None = None
    expected_pl: float = 0.0
    confidence_level: float = 0.0
    risk_level: float = 0.0


class UpcomingDividendEvent(EventBase):
    status: str = ""
    amount: float = 0.0
    dividend_yield: float = 0.0
    currency: str = ""
    payment_date: str | None
    analysis: DividendEventAnalysis | None = None


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
            date=item.get("date", default_vals.get("date")),
            payment_date=item.get("pdate", default_vals.get("pdate")),
            event_category=item.get("cat", default_vals.get("cat", "Dividend")),
            source_name=item.get("src", default_vals.get("src")),
            link=item.get("link", default_vals.get("link")),
            status=item.get("status", default_vals.get("status")),
            amount=item.get("amount", default_vals.get("amount", 0.0)),
            dividend_yield=item.get("yield", default_vals.get("yield", 0.0)),
            currency=item.get("currency", default_vals.get("currency", "")),
        )
        # parse yyyy-MM-dd from event.date into event.timestamp
        event.timestamp = int(datetime.strptime(event.date or "", "%Y-%m-%d").timestamp())
        result.append(event)

    return result


class UpcomingEarningsEvent(EventBase):
    report_period: str | None = None
    status: str | None = None


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
            date=item.get("date", default_vals.get("date")),
            event_category="earnings",
            source_name=item.get("src", default_vals.get("src")),
            link=item.get("link", default_vals.get("link")),
            report_period=item.get("report_period", default_vals.get("report_period")),
            status=item.get("status", default_vals.get("status")),
        )
        # parse yyyy-MM-dd from event.date into event.timestamp
        event.timestamp = int(datetime.strptime(event.date or "", "%Y-%m-%d").timestamp())
        result.append(event)

    return result


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
            if "w2" in v["outlook"]:
                result[k].outlook["w2"] = ListingOutlook(
                    direction=v["outlook"]["w2"].get("dir"),
                    reason=v["outlook"]["w2"].get("reason"),
                    confidence=v["outlook"]["w2"].get("confidence"),
                )
            if "m1" in v["outlook"]:
                result[k].outlook["m1"] = ListingOutlook(
                    direction=v["outlook"]["m1"].get("dir"),
                    reason=v["outlook"]["m1"].get("reason"),
                    confidence=v["outlook"]["m1"].get("confidence"),
                )
            if "m3" in v["outlook"]:
                result[k].outlook["m3"] = ListingOutlook(
                    direction=v["outlook"]["m3"].get("dir"),
                    reason=v["outlook"]["m3"].get("reason"),
                    confidence=v["outlook"]["m3"].get("confidence"),
                )

    return result


class ListingEvent(EventBase):
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
        event = ListingEvent(
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
        # parse yyyy-MM-dd from event.date into event.timestamp
        event.timestamp = int(datetime.strptime(event.date or "", "%Y-%m-%d").timestamp())
        result.append(event)

    return result
