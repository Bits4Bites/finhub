import datetime
import logging
import random
import time
from zoneinfo import ZoneInfo

import cloudscraper
from bs4 import BeautifulSoup
import pandas as pd

from playwright.async_api import async_playwright, Page


def extract_data_table_from_html(html_content: str, table_attr_filter: dict[str, str] = None) -> pd.DataFrame:
    """
    Extracts data from the given HTML content, assuming main content is in a table, and returns it as a Pandas DataFrame.

    Args:
        html_content (str): The HTML content to parse.
        table_attr_filter (dict[str, str], optional): A dictionary of attribute name and values to filter the table.
            For example, {"id": "event-content"} to find a table with id="event-content".
    """
    soup = BeautifulSoup(html_content, "html.parser")

    # Find the main data table
    table = soup.find("table", attrs=table_attr_filter)
    if not table:
        return pd.DataFrame()

    # 1. Extract the table headers
    headers_list = []
    thead = table.find("thead")
    if thead:
        for th in thead.find_all("th"):
            headers_list.append(th.text.strip())
    else:
        # Fallback in case there is no <thead> tag
        headers_list = [th.text.strip() for th in table.find("tr").find_all("th")]

    # 2. Extract the table rows
    data = []
    tbody = table.find("tbody")
    rows = tbody.find_all("tr") if tbody else table.find_all("tr")[1:]

    for row in rows:
        cols = row.find_all("td")
        # Clean up the text (removes excess newlines/spaces common in stock tickers)
        cols_text = [" ".join(ele.text.split()) for ele in cols]

        if cols_text:  # Ensure the row is not empty
            data.append(cols_text)

    if len(data) == 0:
        return pd.DataFrame()

    # 3. Create a Pandas DataFrame for neat formatting
    # Note: Sometimes the website has a hidden column for mobile views.
    # We slice data/headers to match lengths just in case.
    min_length = min(len(headers_list), len(data[0]))
    headers_list = headers_list[:min_length]
    data = [row[:min_length] for row in data]

    df = pd.DataFrame(data, columns=headers_list)
    return df


async def fetch_webpage_content(url: str, retries: int = 3, backoff_factor: float = 0.5) -> str | None:
    """
    Fetches the content of a webpage, with retry logic.

    Args:
        url (str): The URL of the webpage to fetch.
        retries (int, optional): Number of times to retry the request in case of failure. Defaults to 3.
        backoff_factor (float, optional): Factor for calculating sleep time between retries. Defaults to 0.5.
    Returns:
        str: The content of the webpage if successful, otherwise None.
    """
    scraper = cloudscraper.create_scraper()
    for attempt in range(retries):
        try:
            response = scraper.get(url, timeout=10)
            response.raise_for_status()  # Raise an exception for HTTP errors
            return response.text
        except Exception as e:
            logging.warning(f"Fetching attempt {attempt + 1} failed for URL: {url}. Error: {e}")
            if attempt < retries - 1:
                sleep_time = backoff_factor * (2**attempt) + random.uniform(0, 0.1)  # Exponential backoff
                logging.info(f"Retrying after {sleep_time:.2f} seconds...")
                time.sleep(sleep_time)
    logging.error(f"All {retries} fetching attempts failed for URL: {url}.")
    return None


async def fetch_webpage_content_playwright(
    url: str, after_load_func_async=None, retries: int = 2, backoff_factor: float = 0.5
) -> str | None:
    """
    Fetches the content of a webpage using Playwright, with retry logic.

    Args:
        url (str): The URL of the webpage to fetch.
        after_load_func_async (callable, optional): A function to execute after the page has loaded, for additional interactions.
        retries (int, optional): Number of times to retry the request in case of failure. Defaults to 2.
        backoff_factor (float, optional): Factor for calculating sleep time between retries. Defaults to 0.5.
    Returns:
        str: The content of the webpage if successful, otherwise None.
    """
    for attempt in range(retries):
        try:
            async with async_playwright() as p:
                browser = await p.webkit.launch(headless=True)
                page = await browser.new_page()
                await page.goto(url, timeout=60000)
                if after_load_func_async:
                    await after_load_func_async(page)
                page_content = await page.content()
                await browser.close()
                return page_content
        except Exception as e:
            logging.warning(f"Playwright fetching attempt {attempt + 1} failed for URL: {url}. Error: {e}")
            if attempt < retries - 1:
                sleep_time = backoff_factor * (2**attempt) + random.uniform(0, 0.1)  # Exponential backoff
                logging.info(f"Retrying after {sleep_time:.2f} seconds...")
                time.sleep(sleep_time)
    logging.error(f"All {retries} Playwright fetching attempts failed for URL: {url}.")
    return None


async def scrape_data_table(url: str, table_attr_filter: dict[str, str] = None) -> pd.DataFrame:
    """
    Scrapes data from the given URL, assuming main content is in a table, and returns it as a Pandas DataFrame.

    Args:
        url (str): The URL of the webpage containing the data table to scrape.
        table_attr_filter (dict[str, str], optional): A dictionary of attribute name and values to filter the table.
            For example, {"id": "event-content"} to find a table with id="event-content".
    """
    # fetch the webpage content
    logging.info("Fetching data from '%s'...", url)
    html_content = await fetch_webpage_content(url)
    if not html_content:
        logging.error("Failed to fetch content from '%s'.", url)
        return pd.DataFrame()

    # parse the HTML content and extract the data table
    logging.info("Extracting data table from the fetched content...")
    data_table_df = extract_data_table_from_html(html_content, table_attr_filter)

    if data_table_df.empty:
        logging.warning("No data table found in the content from '%s'.", url)

    return data_table_df


async def scrape_data_table_playwright(
    url: str, after_load_func_async=None, table_attr_filter: dict[str, str] = None
) -> pd.DataFrame:
    """
    Scrapes data from the given URL using Playwright, assuming main content is in a table, and returns it as a Pandas DataFrame.

    Args:
        url (str): The URL of the webpage containing the data table to scrape.
        after_load_func_async (callable, optional): A function to execute after the page has loaded, for additional interactions.
        table_attr_filter (dict[str, str], optional): A dictionary of attribute name and values to filter the table.
            For example, {"id": "event-content"} to find a table with id="event-content".
    """
    # fetch the webpage content
    logging.info("Fetching data from '%s'...", url)
    html_content = await fetch_webpage_content_playwright(url, after_load_func_async)
    if not html_content:
        logging.error("Failed to fetch content from '%s'.", url)
        return pd.DataFrame()

    # parse the HTML content and extract the data table
    logging.info("Extracting data table from the fetched content...")
    data_table_df = extract_data_table_from_html(html_content, table_attr_filter)

    if data_table_df.empty:
        logging.warning("No data table found in the content from '%s'.", url)

    return data_table_df


async def scrape_dividends_from_tipranks(
    url_template: str,
    end_date: datetime.date = datetime.date.today() + datetime.timedelta(days=1),
    tz_name: str = "UTC",
    use_playwright: bool = False,
    after_load_func_async=None,
) -> pd.DataFrame:
    """
    Scrapes dividend data from the TipRanks website for a given URL template and end date.

    Args:
        url_template (str): The URL template for scraping data, with a placeholder for the date (e.g., "https://www.tipranks.com/calendars/dividends/{date}").
        end_date (datetime.date): The end date for scraping data. The function will scrape data from the current date up to this end date.
        tz_name (str): The name of the timezone to use for date calculations (e.g., "Australia/Sydney").
        use_playwright (bool): Whether to use Playwright for fetching the webpage content.
        after_load_func_async (callable, optional): A function to execute after the page has loaded, for additional interactions when using Playwright.
    """
    start_date = datetime.datetime.now(ZoneInfo(tz_name)).date()

    # if weekend, move to next Tuesday
    if start_date.weekday() >= 5:  # Saturday or Sunday
        start_date += datetime.timedelta(days=(1 + 7 - start_date.weekday()))
    else:
        start_date += datetime.timedelta(days=1)  # start from next day

    final_df = pd.DataFrame()
    while start_date <= end_date:
        if start_date.weekday() >= 5:  # skip if weekend
            start_date += datetime.timedelta(days=1)
            continue

        target_url = url_template.format(date=start_date.strftime("%Y-%m-%d"))
        df = (
            await scrape_data_table_playwright(target_url, after_load_func_async)
            if use_playwright
            else await scrape_data_table(target_url)
        )
        if not df.empty:
            # add column "Ex-Dividend Date" and fill it with the current date
            df["Ex-Dividend Date"] = start_date.strftime("%Y-%m-%d")
            final_df = pd.concat([final_df, df], ignore_index=True)

        # delay randomly a few seconds to avoid overwhelming the server
        delay_seconds = random.uniform(0.25, 1.00)
        time.sleep(delay_seconds)

        start_date += datetime.timedelta(days=1)

    # before returning result:
    # - remove non-essential columns
    cols_to_drop = ["Analyst Consensus", "Smart Score", "Payout Ratio", "Follow", "Market Cap"]
    for col in cols_to_drop:
        if col in final_df.columns:
            final_df = final_df.drop(columns=[col])
    # - rename column "Name" to "Symbol"
    if "Name" in final_df.columns:
        final_df = final_df.rename(columns={"Name": "Symbol"})
    # - reorder columns to have "Symbol" first, then "Ex-Dividend Date", then the rest
    cols = final_df.columns.tolist()
    if "Symbol" in cols and "Ex-Dividend Date" in cols:
        cols.remove("Symbol")
        cols.remove("Ex-Dividend Date")
        final_df = final_df[["Symbol", "Ex-Dividend Date"] + cols]

    return final_df


async def scrape_dividends_from_tipranks_playwright(
    url_template: str,
    after_load_func_async=None,
    end_date: datetime.date = datetime.date.today() + datetime.timedelta(days=1),
    tz_name: str = "UTC",
) -> pd.DataFrame:
    """
    Scrapes dividend data from the TipRanks website for a given URL template and end date, using Playwright.

    Args:
        url_template (str): The URL template for scraping data, with a placeholder for the date (e.g., "https://www.tipranks.com/calendars/dividends/{date}").
        after_load_func_async (callable, optional): A function to execute after the page has loaded, for additional interactions.
        end_date (datetime.date): The end date for scraping data. The function will scrape data from the current date up to this end date.
        tz_name (str): The name of the timezone to use for date calculations (e.g., "Australia/Sydney").
    """
    return await scrape_dividends_from_tipranks(
        url_template, end_date, tz_name, use_playwright=True, after_load_func_async=after_load_func_async
    )


async def scrape_dividends_asx(end_date: datetime.date) -> pd.DataFrame:
    """
    Scrapes dividend data from the TipRanks website for Australian stocks.

    Args:
        end_date (datetime.date): The end date for scraping data. The function will scrape data from the current date up to this end date.
    """
    url_template = "https://www.tipranks.com/calendars/dividends/{date}/australia"
    tz = "Australia/Sydney"
    df = await scrape_dividends_from_tipranks(url_template, end_date, tz)

    # before returning result:
    # - add column "Exchange Name" with value "ASX"
    df["Exchange Name"] = "ASX"

    return df


async def tipranks_after_load_func(page: Page):
    # rfrm = page.locator("div[id='credential_picker_container']")
    # if rfrm:
    #     print("Removing Credential Picker form (blocking UI)...")
    #     await rfrm.evaluate("el => el.remove()")

    gads = page.locator("div[data-google-query-id]")
    count_gads = await gads.count() if gads else 0
    if count_gads > 0:
        for i in range(count_gads):
            print(f"Removing Google Ads (blocking UI) {i + 1}/{count_gads}...")
            await gads.nth(i).evaluate("el => el.remove()")
    else:
        gads = page.locator("div[id='AdThrive_Footer_1_desktop']")
        if gads:
            print("Removing Google Ads[AdThrive_Footer_1_desktop] (blocking UI)...")
            await gads.evaluate("el => el.remove()")
        gads = page.locator("div[id='AdThrive_Header_1_desktop']")
        if gads:
            print("Removing Google Ads[AdThrive_Header_1_desktop] (blocking UI)...")
            await gads.evaluate("el => el.remove()")

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


async def scrape_dividends_us(end_date: datetime.date) -> pd.DataFrame:
    """
    Scrapes dividend data from the MarketBeat website for US stocks.

    Args:
        end_date (datetime.date): The end date for scraping data. The function will scrape data from the current date up to this end date.
    """
    url_template = "https://www.tipranks.com/calendars/dividends/{date}"
    tz = "America/New_York"
    return await scrape_dividends_from_tipranks_playwright(url_template, tipranks_after_load_func, end_date, tz)


async def scrape_dividends_vn(end_date: datetime.date) -> pd.DataFrame:
    """
    Scrapes dividend data from the VietStock website for VN stocks.

    Args:
        end_date (datetime.date): The end date for scraping data. The function will scrape data from the current date up to this end date.
    """
    url_template = "https://finance.vietstock.vn/lich-su-kien.htm?from={s_date}&to={e_date}&page={page}&tab=1&group=13"
    tz_name = "Asia/Ho_Chi_Minh"
    start_date = datetime.datetime.now(ZoneInfo(tz_name)).date()

    # if weekend, move to next Tuesday
    if start_date.weekday() >= 5:  # Saturday or Sunday
        start_date += datetime.timedelta(days=(1 + 7 - start_date.weekday()))
    else:
        start_date += datetime.timedelta(days=1)  # start from next day

    final_df = pd.DataFrame()
    page = 1
    while True:
        if start_date.weekday() >= 5:  # skip if weekend
            start_date += datetime.timedelta(days=1)
            continue

        target_url = url_template.format(
            s_date=start_date.strftime("%Y-%m-%d"),
            e_date=end_date.strftime("%Y-%m-%d"),
            page=page,
        )
        df = await scrape_data_table_playwright(target_url, None, {"id": "event-content"})
        if df.empty or len(df.columns) < 2:
            break
        final_df = pd.concat([final_df, df], ignore_index=True)

        # delay randomly a few seconds to avoid overwhelming the server
        delay_seconds = random.uniform(0.25, 1.00)
        time.sleep(delay_seconds)

        page += 1

    # before returning result:
    # - remove non-essential columns
    cols_to_drop = ["STT", "Nội dung sự kiện", "Ngày ĐKCC"]
    for col in cols_to_drop:
        if col in final_df.columns:
            final_df = final_df.drop(columns=[col])
    # - rename columns:
    #   - "Mã CK" to "Symbol"
    #   - "Sàn" to "Exchange"
    #   - "Ngày GDKHQ▼" to "Ex-Dividend Date"
    #   - "Tỷ lệ": "Dividend Yield",
    #   - "Ngày thực hiện" to "Payment Date"
    rename_map = {
        "Mã CK": "Symbol",
        "Sàn": "Exchange Name",
        "Ngày GDKHQ▼": "Ex-Dividend Date",
        "Tỷ lệ": "Dividend Yield",
        "Ngày thực hiện": "Payment Date",
    }
    for old_col, new_col in rename_map.items():
        if old_col in final_df.columns:
            final_df = final_df.rename(columns={old_col: new_col})
    # Upper case column "Exchange Name"
    if "Exchange Name" in final_df.columns:
        final_df["Exchange Name"] = final_df["Exchange Name"].str.upper()
    # "Ex-Dividend Date" and "Payment Date" are in format "dd/MM/yyyy", convert to "yyyy-MM-dd"
    for date_col in ["Ex-Dividend Date", "Payment Date"]:
        if date_col in final_df.columns:
            final_df[date_col] = pd.to_datetime(final_df[date_col], format="%d/%m/%Y").dt.strftime("%Y-%m-%d")
    # - Add column "Dividend Amount" = "Dividend Yield" * 10000
    if "Dividend Yield" in final_df.columns:
        final_df["Dividend Amount"] = final_df["Dividend Yield"].str.replace("%", "").astype(float) * 100

    return final_df


async def scrape_earnings_from_tipranks(
    url_template: str,
    end_date: datetime.date = datetime.date.today() + datetime.timedelta(days=1),
    tz_name: str = "UTC",
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
            await scrape_data_table_playwright(target_url, after_load_func_async)
            if use_playwright
            else await scrape_data_table(target_url)
        )
        if not df.empty:
            # add column "Announcement Date" and fill it with the current date
            df["Announcement Date"] = start_date.strftime("%Y-%m-%d")
            final_df = pd.concat([final_df, df], ignore_index=True)

        # delay randomly a few seconds to avoid overwhelming the server
        delay_seconds = random.uniform(0.25, 1.00)
        time.sleep(delay_seconds)

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
    after_load_func_async=None,
    end_date: datetime.date = datetime.date.today() + datetime.timedelta(days=1),
    tz_name: str = "UTC",
) -> pd.DataFrame:
    """
    Scrapes earnings announcement data from the TipRanks website for a given URL template and end date, using Playwright.

    Args:
        url_template (str): The URL template for scraping data, with a placeholder for the date (e.g., "https://www.tipranks.com/calendars/dividends/{date}").
        after_load_func_async (callable, optional): A function to execute after the page has loaded, for additional interactions.
        end_date (datetime.date): The end date for scraping data. The function will scrape data from the current date up to this end date.
        tz_name (str): The name of the timezone to use for date calculations (e.g., "Australia/Sydney").
    """
    return await scrape_earnings_from_tipranks(
        url_template, end_date, tz_name, use_playwright=True, after_load_func_async=after_load_func_async
    )


async def scrape_earnings_asx(end_date: datetime.date) -> pd.DataFrame:
    """
    Scrapes earnings announcement data from the TipRanks website for Australian stocks.

    Args:
        end_date (datetime.date): The end date for scraping data. The function will scrape data from the current date up to this end date.
    """
    url_template = "https://www.tipranks.com/calendars/earnings/{date}/australia"
    tz = "Australia/Sydney"
    return await scrape_earnings_from_tipranks(url_template, end_date, tz)


async def scrape_earnings_us(end_date: datetime.date) -> pd.DataFrame:
    """
    Scrapes earnings announcement data from the TipRanks website for US stocks.

    Args:
        end_date (datetime.date): The end date for scraping data. The function will scrape data from the current date up to this end date.
    """
    url_template = "https://www.tipranks.com/calendars/earnings/{date}"
    tz = "America/New_York"
    return await scrape_earnings_from_tipranks_playwright(url_template, tipranks_after_load_func, end_date, tz)
