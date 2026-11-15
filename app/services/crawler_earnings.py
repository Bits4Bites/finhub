import asyncio
import datetime
import random
import zoneinfo

import pandas as pd
from playwright import async_api as playwright_async_api

from . import crawler_core


async def tipranks_after_load_func(page: playwright_async_api.Page) -> None:
    """Prepare a TipRanks earnings page to expose its exchange column.

    Args:
        page: A loaded Playwright page for the TipRanks earnings calendar.

    Returns:
        ``None`` after any present blocking advertisements are hidden and the
        exchange column is selected. Missing controls are accepted and leave the
        page unchanged.

    Raises:
        playwright.async_api.Error: If Playwright cannot inspect or interact
            with an element that is present.
    """
    gads = page.locator("div[data-google-query-id]")
    count_gads = await gads.count()
    if count_gads > 0:
        for i in range(count_gads):
            await gads.nth(i).evaluate("el => el.style.setProperty('display', 'none');")
    else:
        for selector in ("div[id='AdThrive_Footer_1_desktop']", "div[id='AdThrive_Header_1_desktop']"):
            fallback_ad = page.locator(selector)
            if await fallback_ad.count() > 0:
                await fallback_ad.evaluate("el => el.style.setProperty('display', 'none');")

    btn = page.locator("button[data-id='select-columns-button']")
    if await btn.count() > 0:
        await btn.click()

    checkbox = page.locator("label[title='Exchange Name']")
    if await checkbox.count() > 0:
        await checkbox.click()

    btn = page.locator("button[id='save']")
    if await btn.count() > 0:
        await btn.click()


async def scrape_earnings_from_tipranks(
    url_template: str,
    end_date: datetime.date | None = None,
    tz_name: str = "UTC",
    *,
    use_playwright: bool = False,
    after_load_func_async=None,
) -> pd.DataFrame:
    """Collect upcoming weekday earnings announcements from TipRanks.

    Args:
        url_template: Calendar URL containing a ``{date}`` placeholder.
        end_date: Inclusive final announcement date. When omitted, it is
            resolved at call time as one day after the first eligible weekday.
        tz_name: IANA timezone used to determine today.
        use_playwright: Use browser rendering instead of the HTTP-first table
            crawler.
        after_load_func_async: Optional async page-preparation callback used only
            with Playwright.

    Returns:
        Combined source rows for weekdays in the requested range. ``Name`` is
        normalized to ``Symbol``, ``Announcement Date`` is added in
        ``YYYY-MM-DD`` format, non-event metric columns are removed, and
        ``Symbol`` and ``Announcement Date`` lead the output when present.
        Returns an empty DataFrame when the range has no eligible rows or every
        page is unavailable.

    Raises:
        ZoneInfoNotFoundError: If ``tz_name`` is invalid.
        ValueError: If a non-empty TipRanks table does not identify a symbol.

    Notes:
        Weekend dates are skipped. Individual page-fetch failures are represented
        by empty page results and do not stop later dates.
    """
    start_date = datetime.datetime.now(zoneinfo.ZoneInfo(tz_name)).date()

    if start_date.weekday() >= 5:
        start_date += datetime.timedelta(days=(7 - start_date.weekday()))
    if end_date is None:
        end_date = start_date + datetime.timedelta(days=1)

    final_df = pd.DataFrame()
    while start_date <= end_date:
        if start_date.weekday() >= 5:
            start_date += datetime.timedelta(days=1)
            continue

        target_url = url_template.format(date=start_date.strftime("%Y-%m-%d"))
        df = (
            await crawler_core.scrape_data_table_playwright(target_url, after_load_func_async=after_load_func_async)
            if use_playwright
            else await crawler_core.scrape_data_table(target_url)
        )
        if not df.empty:
            df["Announcement Date"] = start_date.strftime("%Y-%m-%d")
            final_df = pd.concat([final_df, df], ignore_index=True)

        delay_seconds = random.uniform(1.00, 3.00)
        await asyncio.sleep(delay_seconds)

        start_date += datetime.timedelta(days=1)

    cols_to_drop = [
        "Market Cap",
        "EPS (Forecast)",
        "EPS (Actual)",
        "Revenue (Forecast)",
        "Revenue (Actual)",
        "Analyst Consensus",
        "Smart Score",
        "Time",
        "Follow",
    ]
    final_df = final_df.drop(columns=cols_to_drop, errors="ignore")
    if not final_df.empty and "Name" not in final_df.columns and "Symbol" not in final_df.columns:
        raise ValueError("TipRanks earnings table is missing the Name column")
    if "Name" in final_df.columns:
        final_df = final_df.rename(columns={"Name": "Symbol"})
    cols = final_df.columns.tolist()
    if "Symbol" in cols and "Announcement Date" in cols:
        cols.remove("Symbol")
        cols.remove("Announcement Date")
        final_df = final_df[["Symbol", "Announcement Date"] + cols]

    return final_df


async def scrape_earnings_from_tipranks_playwright(
    url_template: str,
    end_date: datetime.date | None = None,
    tz_name: str = "UTC",
    *,
    after_load_func_async=None,
) -> pd.DataFrame:
    """Collect TipRanks earnings announcements from browser-rendered pages.

    Args:
        url_template: Calendar URL containing a ``{date}`` placeholder.
        end_date: Inclusive final announcement date, resolved at call time when
            omitted.
        tz_name: IANA timezone used to determine today.
        after_load_func_async: Optional async callback that prepares each page
            before table extraction.

    Returns:
        The same normalized DataFrame contract as
        :func:`scrape_earnings_from_tipranks`, or an empty DataFrame when no
        announcement rows are available.

    Raises:
        ZoneInfoNotFoundError: If ``tz_name`` is invalid.
        ValueError: If a non-empty TipRanks table does not identify a symbol.
    """
    return await scrape_earnings_from_tipranks(
        url_template, end_date, tz_name, use_playwright=True, after_load_func_async=after_load_func_async
    )


async def scrape_earnings_asx(end_date: datetime.date) -> pd.DataFrame:
    """Return upcoming Australian earnings announcements from TipRanks.

    Args:
        end_date: Inclusive final announcement date in Sydney time.

    Returns:
        Normalized earnings rows with ``Symbol`` and ``Announcement Date`` first,
        or an empty DataFrame when no rows are available.

    Raises:
        ZoneInfoNotFoundError: If the configured Sydney timezone is unavailable.
        ValueError: If a non-empty source table does not identify a symbol.
    """
    url_template = "https://www.tipranks.com/calendars/earnings/{date}/australia"
    tz = "Australia/Sydney"
    return await scrape_earnings_from_tipranks(url_template, end_date, tz)


async def scrape_earnings_us(end_date: datetime.date) -> pd.DataFrame:
    """Return upcoming US earnings announcements from TipRanks.

    Args:
        end_date: Inclusive final announcement date in New York time.

    Returns:
        Browser-rendered normalized earnings rows, including ``Exchange Name``
        when TipRanks exposes it, or an empty DataFrame when no rows are
        available.

    Raises:
        ZoneInfoNotFoundError: If the configured New York timezone is
            unavailable.
        ValueError: If a non-empty source table does not identify a symbol.

    Notes:
        The browser callback requests TipRanks' optional exchange column so the
        event service can exclude unsupported US venues.
    """
    url_template = "https://www.tipranks.com/calendars/earnings/{date}"
    tz = "America/New_York"
    return await scrape_earnings_from_tipranks_playwright(
        url_template, end_date, tz, after_load_func_async=tipranks_after_load_func
    )
