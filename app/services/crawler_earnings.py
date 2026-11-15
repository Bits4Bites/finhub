import asyncio
import datetime
import random
from zoneinfo import ZoneInfo

import pandas as pd
from playwright import async_api as playwright_async_api

from . import crawler_core


async def tipranks_after_load_func(page: playwright_async_api.Page):
    # rfrm = page.locator("div[id='credential_picker_container']")
    # if rfrm:
    #     print("Removing Credential Picker form (blocking UI)...")
    #     await rfrm.evaluate("el => el.remove()")
    #     # await rfrm.evaluate("el => el.style.setProperty('display', 'none');")

    gads = page.locator("div[data-google-query-id]")
    count_gads = await gads.count() if gads else 0
    if count_gads > 0:
        for i in range(count_gads):
            print(f"Removing Google Ads (blocking UI) {i + 1}/{count_gads}...")
            # await gads.nth(i).evaluate("el => el.remove()")
            await gads.evaluate("el => el.style.setProperty('display', 'none');")
    else:
        gads = page.locator("div[id='AdThrive_Footer_1_desktop']")
        if gads:
            print("Removing Google Ads[AdThrive_Footer_1_desktop] (blocking UI)...")
            # await gads.evaluate("el => el.remove()")
            await gads.evaluate("el => el.style.setProperty('display', 'none');")
        gads = page.locator("div[id='AdThrive_Header_1_desktop']")
        if gads:
            print("Removing Google Ads[AdThrive_Header_1_desktop] (blocking UI)...")
            # await gads.evaluate("el => el.remove()")
            await gads.evaluate("el => el.style.setProperty('display', 'none');")

    btn = page.locator("button[data-id='select-columns-button']")
    if btn:
        print("Clicking the button to select columns...")
        await btn.click()
    else:
        print("Button[data-id='select-columns-button'] not found!")

    checkbox = page.locator("label[title='Exchange Name']")
    if checkbox:
        print("Clicking the checkbox to add 'Exchange Name' column...")
        await checkbox.click()
    else:
        print("Label[title='Exchange Name'] not found!")

    btn = page.locator("button[id='save']")
    if btn:
        print("Clicking the save button...")
        await btn.click()
    else:
        print("Button[id='save'] not found!")


async def scrape_earnings_from_tipranks(
    url_template: str,
    end_date: datetime.date = datetime.date.today() + datetime.timedelta(days=1),
    tz_name: str = "UTC",
    *,
    use_playwright: bool = False,
    after_load_func_async=None,
) -> pd.DataFrame:
    """
    Scrapes earnings announcement data from a given URL template and end date.

    Args:
        url_template (str): The URL template for scraping data, with a placeholder for the date (e.g., "https://www.tipranks.com/calendars/earnings/{date}").
        end_date (datetime.date): The end date for scraping data. The function will scrape data from the current date up to this end date.
        tz_name (str): The name of the timezone to use for date calculations (e.g., "Australia/Sydney").
        use_playwright (bool): Whether to use Playwright for fetching the webpage content.
        after_load_func_async (callable, optional): A function to execute after the page has loaded, for additional interactions when using Playwright.

    Returns:
        DataFrame: A Pandas DataFrame containing the data table extracted from the webpage.
    """
    start_date = datetime.datetime.now(ZoneInfo(tz_name)).date()

    # if weekend, move to next Monday
    if start_date.weekday() >= 5:  # Saturday or Sunday
        start_date += datetime.timedelta(days=(7 - start_date.weekday()))

    final_df = pd.DataFrame()
    while start_date <= end_date:
        if start_date.weekday() >= 5:  # skip if weekend
            start_date += datetime.timedelta(days=1)
            continue

        target_url = url_template.format(date=start_date.strftime("%Y-%m-%d"))
        df = (
            await crawler_core.scrape_data_table_playwright(target_url, after_load_func_async=after_load_func_async)
            if use_playwright
            else await crawler_core.scrape_data_table(target_url)
        )
        if not df.empty:
            # add column "Announcement Date" and fill it with the current date
            df["Announcement Date"] = start_date.strftime("%Y-%m-%d")
            final_df = pd.concat([final_df, df], ignore_index=True)

        # delay randomly a few seconds to avoid overwhelming the server
        delay_seconds = random.uniform(1.00, 3.00)
        await asyncio.sleep(delay_seconds)

        start_date += datetime.timedelta(days=1)

    # before returning result:
    # - remove non-essential columns
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
    for col in cols_to_drop:
        if col in final_df.columns:
            final_df = final_df.drop(columns=[col])
    # - rename column "Name" to "Symbol"
    if "Name" in final_df.columns:
        final_df = final_df.rename(columns={"Name": "Symbol"})
    # - reorder columns to have "Symbol" first, then "Announcement Date", then the rest
    cols = final_df.columns.tolist()
    if "Symbol" in cols and "Announcement Date" in cols:
        cols.remove("Symbol")
        cols.remove("Announcement Date")
        final_df = final_df[["Symbol", "Announcement Date"] + cols]

    return final_df


async def scrape_earnings_from_tipranks_playwright(
    url_template: str,
    end_date: datetime.date = datetime.date.today() + datetime.timedelta(days=1),
    tz_name: str = "UTC",
    *,
    after_load_func_async=None,
) -> pd.DataFrame:
    """
    Scrapes earnings announcement data from the TipRanks website for a given URL template and end date, using Playwright.

    Args:
        url_template (str): The URL template for scraping data, with a placeholder for the date (e.g., "https://www.tipranks.com/calendars/dividends/{date}").
        after_load_func_async (callable, optional): A function to execute after the page has loaded, for additional interactions.
        end_date (datetime.date): The end date for scraping data. The function will scrape data from the current date up to this end date.
        tz_name (str): The name of the timezone to use for date calculations (e.g., "Australia/Sydney").

    Returns:
        DataFrame: A Pandas DataFrame containing the data table extracted from the webpage.
    """
    return await scrape_earnings_from_tipranks(
        url_template, end_date, tz_name, use_playwright=True, after_load_func_async=after_load_func_async
    )


async def scrape_earnings_asx(end_date: datetime.date) -> pd.DataFrame:
    """
    Scrapes earnings announcement data from the TipRanks website for Australian stocks.

    Args:
        end_date (datetime.date): The end date for scraping data. The function will scrape data from the current date up to this end date.

    Returns:
        DataFrame: A Pandas DataFrame containing the data table extracted from the webpage.
    """
    url_template = "https://www.tipranks.com/calendars/earnings/{date}/australia"
    tz = "Australia/Sydney"
    return await scrape_earnings_from_tipranks(url_template, end_date, tz)


async def scrape_earnings_us(end_date: datetime.date) -> pd.DataFrame:
    """
    Scrapes earnings announcement data from the TipRanks website for US stocks.

    Args:
        end_date (datetime.date): The end date for scraping data. The function will scrape data from the current date up to this end date.

    Returns:
        DataFrame: A Pandas DataFrame containing the data table extracted from the webpage.
    """
    url_template = "https://www.tipranks.com/calendars/earnings/{date}"
    tz = "America/New_York"
    return await scrape_earnings_from_tipranks_playwright(
        url_template, end_date, tz, after_load_func_async=tipranks_after_load_func
    )
