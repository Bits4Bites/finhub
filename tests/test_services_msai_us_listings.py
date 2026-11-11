import asyncio
import datetime
import zoneinfo
from unittest import mock

import pandas as pd
import pytest

from app.services import msai_us_listings


def _listing_row(symbol: str = "EXAMPLE", **overrides) -> dict[str, object]:
    row: dict[str, object] = {
        "IPO Date": "Nov 12, 2026",
        "Symbol": symbol,
        "Company Name": "Example Inc.",
        "Exchange": "NASDAQ",
        "Price Range": "$11.00 - $13.00",
        "Shares Offered": "10,000,000",
        "Deal Size": "200.00M",
        "Market Cap": "1.29B",
        "Revenue": "49.68M",
    }
    row.update(overrides)
    return row


def test_extracts_prices_and_deal_sizes_from_all_three_tables():
    tables = [
        pd.DataFrame([_listing_row(" range ", **{"Exchange": "Nasdaq Global Select", "Company Name": " Range Inc. "})]),
        pd.DataFrame(
            [
                _listing_row(
                    "FIXED",
                    **{
                        "IPO Date": "Jul 15, 2027",
                        "Exchange": "NYSE",
                        "Price Range": "$12.50",
                        "Deal Size": "$1.25B",
                    },
                )
            ]
        ),
        pd.DataFrame(
            [
                _listing_row("SMALL", **{"Price Range": 1.25, "Deal Size": "1.001K"}),
                _listing_row("RANGE", **{"Price Range": "$100.00"}),
            ]
        ),
    ]

    with mock.patch.object(
        msai_us_listings.services_crawler,
        "scrape_data_table",
        new_callable=mock.AsyncMock,
        side_effect=tables,
    ) as mock_scrape:
        events = asyncio.run(msai_us_listings._get_us_new_listings())

    assert [event.symbol for event in events] == ["NASDAQ:RANGE", "NYSE:FIXED", "NASDAQ:SMALL"]
    ranged, fixed, small = events
    assert ranged.exchange == "NASDAQ"
    assert ranged.company_name == "Range Inc."
    assert ranged.issue_price == 11
    assert ranged.issue_price_upper == 13
    assert ranged.capital_to_raise == 200_000_000
    assert fixed.issue_price == 12.5
    assert fixed.issue_price_upper is None
    assert fixed.capital_to_raise == 1_250_000_000
    assert small.issue_price == 1.25
    assert small.issue_price_upper is None
    assert small.capital_to_raise == 1001
    ny_tz = zoneinfo.ZoneInfo("America/New_York")
    assert ranged.timestamp_str == "2026-11-12"
    assert ranged.timestamp == int(datetime.datetime(2026, 11, 12, tzinfo=ny_tz).timestamp())
    assert fixed.timestamp_str == "2027-07-15"
    assert fixed.timestamp == int(datetime.datetime(2027, 7, 15, tzinfo=ny_tz).timestamp())
    for event in events:
        assert event.currency == "USD"
        assert event.event_category == "listing"
        assert event.source_name == "Stock Analysis"
        assert event.link == "https://stockanalysis.com/ipos/calendar/"
    assert mock_scrape.await_args_list == [
        mock.call(
            "https://stockanalysis.com/ipos/calendar/",
            table_attr_filter={"id": "main-table"},
            filter_skip=index,
        )
        for index in range(3)
    ]


@pytest.mark.parametrize("unavailable", [None, float("nan"), pd.NA, "-", "N/A", "TBD"])
def test_retains_listings_with_unavailable_offer_values(unavailable):
    tables = [
        pd.DataFrame(),
        pd.DataFrame([_listing_row(**{"Price Range": unavailable, "Deal Size": unavailable})]),
        pd.DataFrame(),
    ]
    with mock.patch.object(
        msai_us_listings.services_crawler,
        "scrape_data_table",
        new_callable=mock.AsyncMock,
        side_effect=tables,
    ):
        events = asyncio.run(msai_us_listings._get_us_new_listings())

    assert len(events) == 1
    assert events[0].issue_price is None
    assert events[0].issue_price_upper is None
    assert events[0].capital_to_raise is None


def test_invalid_rows_do_not_abort_other_listings():
    tables = [
        pd.DataFrame(
            [
                _listing_row("NODATE", **{"IPO Date": "TBD"}),
                _listing_row("ZERO", **{"Price Range": "$0"}),
                _listing_row("NEGATIVE", **{"Price Range": "-$1"}),
                _listing_row("REVERSED", **{"Price Range": "$13 - $11"}),
                _listing_row("BADPRICE", **{"Price Range": "$11 - TBD"}),
                _listing_row("NONFINITE", **{"Price Range": "Infinity"}),
                _listing_row("ZEROCAP", **{"Deal Size": "0"}),
                _listing_row("FRACTION", **{"Deal Size": "1.5"}),
                _listing_row(**{"Symbol": None}),
                _listing_row("NOEXCHANGE", **{"Exchange": None}),
            ]
        ),
        pd.DataFrame([_listing_row("VALID")]),
        pd.DataFrame(),
    ]
    with mock.patch.object(
        msai_us_listings.services_crawler,
        "scrape_data_table",
        new_callable=mock.AsyncMock,
        side_effect=tables,
    ):
        events = asyncio.run(msai_us_listings._get_us_new_listings())

    assert [event.symbol for event in events] == ["NASDAQ:VALID"]


def test_returns_no_listings_when_calendar_tables_are_empty():
    with mock.patch.object(
        msai_us_listings.services_crawler,
        "scrape_data_table",
        new_callable=mock.AsyncMock,
        side_effect=[pd.DataFrame(), pd.DataFrame(), pd.DataFrame()],
    ):
        events = asyncio.run(msai_us_listings._get_us_new_listings())

    assert events == []
