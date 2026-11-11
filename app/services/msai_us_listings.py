import decimal
import json
import logging
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd
from pydantic import ValidationError

from .. import config
from ..models import events_listings as models_events_listings
from ..services import crawler as services_crawler
from ..utils import cache, conv

_US_LISTINGS_CACHE_NAMESPACE = "us-new-listings-analysis"
_US_LISTINGS_URL = "https://stockanalysis.com/ipos/calendar/"
_US_COUNTRY = "US"
_US_CURRENCY = "USD"
_US_LISTINGS_RESEARCH_TASK = "US_LISTTINGS_RESEARCH"
_US_LISTINGS_ANALYZE_TASK = "US_LISTTINGS_ANALYZE"
_MAX_LISTINGS_TO_ANALYZE = 5
_RESEARCH_SECTION_NAMES = (
    "offer",
    "business",
    "financials",
    "valuation",
    "governance",
    "market_context",
    "risks_and_catalysts",
)
_ANALYSIS_SECTION_NAMES = (
    "executive_summary",
    "offer",
    "business",
    "financials",
    "valuation",
    "governance",
    "risks_and_catalysts",
)
_OUTLOOK_PERIOD_NAMES = ("ipo_day", "first_week", "first_two_weeks", "first_month")
_NY_TZ = ZoneInfo("America/New_York")
_INVALID_DATETIME = "1900-01-01 00:00:00+00:00"


async def ai_get_us_new_listings() -> list[models_events_listings.ListingEvent]:
    """
    Fetch all current or upcoming US listings (TODO: and analyze up to five eligible events).

    Listings before the current New York date are excluded. Today's listings are
    included, and results are ordered by the soonest confirmed listing date. Entries
    without a confirmed date or with supplied non-positive monetary values are
    excluded. Unavailable issue prices and capital amounts are retained as null.
    Economy mode skips analysis for explicitly non-underwritten listings with a
    missing public-offer close date or one before today. Economy-skipped events do
    not consume the analysis limit, but failed analysis attempts do. Once the limit
    is reached, remaining events are returned with their analysis status set to Skipped.
    Upcoming assessments give explicitly subjective base cases anchored to the issue
    price when available, or qualitative views otherwise, with evidence gaps and cautions.
    """
    today = _current_ny_date()
    events = _select_current_and_future_listings(
        await _get_us_new_listings(),
        today=today,
    )
    cache_key = _generate_analysis_cache_key(events, today=today)
    cached_events = await cache.get(cache_key)
    if cached_events is not None:
        return _validate_cached_events(cached_events)

    events = await _analyze_us_listings(events)
    for event in events:
        event.timestamp_str = conv.yyyymmdd_to_iso(event.timestamp_str, _NY_TZ) or _INVALID_DATETIME
        event.timestamp = int(datetime.fromisoformat(event.timestamp_str).timestamp())

    if all(event.analysis_status == "Completed" for event in events):
        await cache.set(
            cache_key,
            [event.model_dump(mode="json") for event in events],
            ttl=_analysis_cache_ttl(events, today=today),
        )
    return events


def _current_ny_date() -> date:
    return datetime.now(_NY_TZ).date()


def _select_current_and_future_listings(
    events: list[models_events_listings.ListingEvent],
    *,
    today: date,
) -> list[models_events_listings.ListingEvent]:
    return sorted(
        (event for event in events if datetime.fromisoformat(event.timestamp_str).date() >= today),
        key=lambda event: (datetime.fromisoformat(event.timestamp_str).date(), event.symbol),
    )


def _generate_analysis_cache_key(
    events: list[models_events_listings.ListingEvent],
    *,
    today: date,
) -> str:
    return cache.generate_hourly_key(
        _US_LISTINGS_CACHE_NAMESPACE,
        today.isoformat(),
        config.settings_llm_task.tokenomics_mode,
        *(
            _task_cache_identity(task_id)
            for task_id in (
                _US_LISTINGS_RESEARCH_TASK,
                _US_LISTINGS_ANALYZE_TASK,
            )
        ),
        *(_event_input_json(event) for event in events),
    )


def _event_input_json(event: models_events_listings.ListingEvent) -> str:
    return event.model_dump_json(
        exclude={"analysis", "analysis_error", "analysis_status", "timestamp"},
        exclude_none=False,
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
            "max_tool_calls": task_config.max_tool_calls,
        },
        sort_keys=True,
    )


def _listing_cache_ttl(
    event: models_events_listings.ListingEvent,
    *,
    today: date,
) -> int:
    days_until_listing = (datetime.fromisoformat(event.timestamp_str).date() - today).days
    if days_until_listing <= 1:
        return 60 * 60
    if days_until_listing <= 7:
        return 6 * 60 * 60
    return 24 * 60 * 60


def _analysis_cache_ttl(
    events: list[models_events_listings.ListingEvent],
    *,
    today: date,
) -> int:
    return min((_listing_cache_ttl(event, today=today) for event in events), default=60 * 60)


def _validate_cached_events(cached_events: object) -> list[models_events_listings.ListingEvent]:
    if not isinstance(cached_events, list):
        raise RuntimeError("ASX listings analysis cache contains an invalid value")
    try:
        return [
            event.model_copy(deep=True)
            if isinstance(event, models_events_listings.ListingEvent)
            else models_events_listings.ListingEvent.model_validate(event)
            for event in cached_events
        ]
    except (TypeError, ValidationError) as exc:
        raise RuntimeError("ASX listings analysis cache contains an invalid value") from exc


async def _get_us_new_listings() -> list[models_events_listings.ListingEvent]:
    """Extract confirmed listing events from the Stock Analysis IPO calendar."""
    url = _US_LISTINGS_URL
    df1 = await services_crawler.scrape_data_table(url, table_attr_filter={"id": "main-table"}, filter_skip=0)
    df2 = await services_crawler.scrape_data_table(url, table_attr_filter={"id": "main-table"}, filter_skip=1)
    df3 = await services_crawler.scrape_data_table(url, table_attr_filter={"id": "main-table"}, filter_skip=2)

    # df1, df2, df3 all have the same columns:
    # - IPO Date: sample "Nov 12, 2026"
    # - Symbol: sample "AAPL"
    # - Company Name: sample "Apple Inc."
    # - Exchange: sample "NASDAQ"
    # - Price Range: sample "$11.00 - $13.00"
    # - Shares Offered: sample "10,000,000"
    # - Deal Size: sample "200.00M"
    # - Market Cap: sample "1.29B"
    # - Revenue: sample "49.68M"

    events: list[models_events_listings.ListingEvent] = []
    seen_symbols: set[str] = set()
    for frame in (df1, df2, df3):
        for row in frame.to_dict(orient="records"):
            try:
                symbol = _listing_cell_text(row.get("Symbol")).upper()
                exchange = conv.normalize_exchange_code(_listing_cell_text(row.get("Exchange")))
                if not exchange or re.fullmatch(r"[A-Z0-9]+(?:[.-][A-Z0-9]+)*", symbol) is None:
                    continue
                listing_at = datetime.strptime(_listing_cell_text(row.get("IPO Date")), "%b %d, %Y").replace(
                    tzinfo=_NY_TZ
                )

                price_text = _listing_cell_text(row.get("Price Range"))
                prices = re.split(r"[-\u2013\u2014]", price_text) if price_text else []
                if len(prices) > 2 or any(not part.strip() for part in prices):
                    raise ValueError("Invalid issue-price range")
                issue_price = _parse_listing_amount(prices[0]) if prices else None
                issue_price_upper = _parse_listing_amount(prices[1]) if len(prices) == 2 else None
                if len(prices) == 2 and (issue_price is None or issue_price_upper is None):
                    raise ValueError("Incomplete issue-price range")

                event = models_events_listings.ListingEvent(
                    symbol=f"{exchange}:{symbol}",
                    exchange=exchange,
                    company_name=_listing_cell_text(row.get("Company Name")) or None,
                    timestamp=int(listing_at.timestamp()),
                    timestamp_str=listing_at.date().isoformat(),
                    event_category="listing",
                    source_name="Stock Analysis",
                    link=url,
                    issue_price=issue_price,
                    issue_price_upper=issue_price_upper,
                    currency=_US_CURRENCY,
                    capital_to_raise=_parse_listing_amount(row.get("Deal Size")),
                )
            except ValueError, decimal.DecimalException:
                logging.warning("[US Listings] Ignoring invalid listing '%s'.", row.get("Symbol"))
                continue
            if event.symbol in seen_symbols:
                continue
            seen_symbols.add(event.symbol)
            events.append(event)
    return events


def _listing_cell_text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text.upper() in {"-", "\u2013", "\u2014", "N/A"} else text


def _parse_listing_amount(value: object) -> decimal.Decimal | None:
    text = _listing_cell_text(value).upper().replace("$", "").replace(",", "")
    if not text or text in {"NA", "TBA", "TBC", "TBD"}:
        return None
    multipliers = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000, "T": 1_000_000_000_000}
    multiplier = multipliers.get(text[-1], 1)
    if text[-1] in multipliers:
        text = text[:-1].strip()
    amount = decimal.Decimal(text) * multiplier
    if not amount.is_finite():
        raise ValueError("Listing amounts must be finite")
    return amount


async def _analyze_us_listings(
    events: list[models_events_listings.ListingEvent],
) -> list[models_events_listings.ListingEvent]:
    # TODO
    return events
