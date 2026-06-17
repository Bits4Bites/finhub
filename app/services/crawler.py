import datetime
import logging
import random
import ssl
import time
from zoneinfo import ZoneInfo

import cloudscraper
import pandas as pd
from bs4 import BeautifulSoup
from playwright.async_api import Page, ProxySettings, ViewportSize, async_playwright

from .. import config

logger = logging.getLogger(__name__)


def extract_data_table_from_html(html_content: str, *, raw_cell_content=False, table_attr_filter=None) -> pd.DataFrame:
    """
    Extracts data from the given HTML content, assuming main content is in a table, and returns it as a Pandas DataFrame.

    Args:
        html_content (str): The HTML content to parse.
        raw_cell_content (bool, optional): If False, cell content will be cleaned-up; otherwise cell's raw content will be returned.
        table_attr_filter (dict[str, str], optional): A dictionary of attribute name and values to filter the table.
            For example, {"id": "event-content"} to find a table with id="event-content".

    Returns:
        DataFrame: A Pandas DataFrame containing the extracted data.
    """
    soup = BeautifulSoup(html_content, "html.parser")

    # Find the main data table
    table = soup.find("table", attrs=table_attr_filter)
    if not table:
        return pd.DataFrame()

    # 1. Extract the table headers
    # headers_list = None
    thead = table.find("thead")
    if thead:
        # for th in thead.find_all("th"):
        #     headers_list.append(th.text.strip())
        headers_list = [th.text.strip() for th in thead.find_all("th")]
        if len(headers_list) == 0:
            headers_list = [td.text.strip() for td in thead.find_all("td")]
    else:
        # Fallback in case there is no <thead> tag
        tr = table.find("tr")
        headers_list = [th.text.strip() for th in (tr.find_all("th") if tr else [])]
        if len(headers_list) == 0:
            headers_list = [td.text.strip() for td in (tr.find_all("td") if tr else [])]

    # 2. Extract the table rows
    data = []
    tbody = table.find("tbody")
    rows = tbody.find_all("tr") if tbody else table.find_all("tr")[1:]

    for row in rows:
        cols = row.find_all("td")
        # Clean up the text (removes excess newlines/spaces common in stock tickers)
        if raw_cell_content:
            cols_text = [("".join(str(child) for child in ele.contents)).strip() for ele in cols]
        else:
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


async def fetch_webpage_content(
    url: str, *, retries: int = 3, backoff_factor: float = 0.5, proxies: list[str] = None
) -> str | None:
    """
    Fetches the content of a webpage, with retry logic.

    Args:
        url (str): The URL of the webpage to fetch.
        retries (int, optional): Number of times to retry the request in case of failure. Defaults to 3.
        backoff_factor (float, optional): Factor for calculating sleep time between retries. Defaults to 0.5.
        proxies (list[str], optional): Optional list http proxies.

    Returns:
        str: The content of the webpage if successful, otherwise None.
    """
    proxies = [] if not proxies else proxies
    unverified_ssl_context = ssl.create_default_context()
    unverified_ssl_context.check_hostname = False
    scraper = cloudscraper.create_scraper(
        browser={"browser": "chrome", "platform": "windows", "desktop": True},
        ssl_context=unverified_ssl_context if proxies else None,
    )
    scraper.verify = not proxies
    for attempt in range(retries):
        http_proxy = random.sample(proxies, 1) if proxies else None
        if http_proxy:
            logger.info("fetch_webpage_content: using proxy %s", http_proxy[0])
        try:
            response = scraper.get(
                url,
                timeout=60,
                proxies={
                    "http": http_proxy[0],
                    "https": http_proxy[0],
                }
                if http_proxy
                else None,
            )
            response.raise_for_status()  # Raise an exception for HTTP errors
            return response.text
        except Exception as e:
            logger.warning(f"Fetching attempt {attempt + 1} failed for URL: {url}. Error: {e}")
            if attempt < retries - 1:
                sleep_time = backoff_factor * (2**attempt) + random.uniform(0, 0.1)  # Exponential backoff
                logger.info(f"Retrying after {sleep_time:.2f} seconds...")
                time.sleep(sleep_time)
    logger.error(f"All {retries} fetching attempts failed for URL: {url}.")
    return None


async def fetch_webpage_content_playwright(
    url: str, *, after_load_func_async=None, retries: int = 2, backoff_factor: float = 0.5, proxies: list[str] = None
) -> str | None:
    """
    Fetches the content of a webpage using Playwright, with retry logic.

    Args:
        url (str): The URL of the webpage to fetch.
        after_load_func_async (callable, optional): A function to execute after the page has loaded, for additional interactions.
        retries (int, optional): Number of times to retry the request in case of failure. Defaults to 2.
        backoff_factor (float, optional): Factor for calculating sleep time between retries. Defaults to 0.5.
        proxies (list[str], optional): Optional list http proxies.

    Returns:
        str: The content of the webpage if successful, otherwise None.
    """
    proxies = [] if not proxies else proxies
    for attempt in range(retries):
        http_proxy = random.sample(proxies, 1) if proxies else None
        if http_proxy:
            logger.info("fetch_webpage_content_playwright: using proxy %s", http_proxy[0])
        try:
            async with async_playwright() as p:
                browser = await p.webkit.launch(
                    headless=True,
                    proxy=ProxySettings(server=http_proxy[0]) if http_proxy else None,
                )
                page = await browser.new_page(
                    ignore_https_errors=not (not http_proxy),
                    screen=ViewportSize(width=1664, height=1110),
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36 Edg/145.0.0.0",
                )
                await page.goto(url, timeout=60000)
                if after_load_func_async:
                    await after_load_func_async(page)
                page_content = await page.content()
                await browser.close()
                return page_content
        except Exception as e:
            logger.warning(f"Playwright fetching attempt {attempt + 1} failed for URL: {url}. Error: {e}")
            if attempt < retries - 1:
                sleep_time = backoff_factor * (2**attempt) + random.uniform(0, 0.1)  # Exponential backoff
                logger.info(f"Retrying after {sleep_time:.2f} seconds...")
                time.sleep(sleep_time)
    logger.error(f"All {retries} Playwright fetching attempts failed for URL: {url}.")
    return None


async def scrape_data_table(
    url: str, *, raw_cell_content=False, table_attr_filter=None, proxies: list[str] = None
) -> pd.DataFrame:
    """
    Scrapes data from the given URL, assuming main content is in a table, and returns it as a Pandas DataFrame.

    Args:
        url (str): The URL of the webpage containing the data table to scrape.
        raw_cell_content (bool, optional): If False, cell content will be cleaned-up; otherwise cell's raw content will be returned.
        table_attr_filter (dict[str, str], optional): A dictionary of attribute name and values to filter the table.
            For example, {"id": "event-content"} to find a table with id="event-content".
        proxies (list[str], optional): Optional list http proxies.

    Returns:
        DataFrame: A Pandas DataFrame containing the data table extracted from the webpage.
    """
    # fetch the webpage content
    logger.info("Fetching data from '%s'...", url)
    html_content = await fetch_webpage_content(url, proxies=proxies)
    if not html_content:
        logger.error("Failed to fetch content from '%s'.", url)
        return pd.DataFrame()

    # parse the HTML content and extract the data table
    logger.info("Extracting data table from the fetched content...")
    data_table_df = extract_data_table_from_html(
        html_content, raw_cell_content=raw_cell_content, table_attr_filter=table_attr_filter
    )

    if data_table_df.empty:
        logger.warning("No data table found in the content from '%s'.", url)

    return data_table_df


async def scrape_data_table_playwright(
    url: str, *, raw_cell_content=False, after_load_func_async=None, table_attr_filter=None, proxies: list[str] = None
) -> pd.DataFrame:
    """
    Scrapes data from the given URL using Playwright, assuming main content is in a table, and returns it as a Pandas DataFrame.

    Args:
        url (str): The URL of the webpage containing the data table to scrape.
        raw_cell_content (bool, optional): If False, cell content will be cleaned-up; otherwise cell's raw content will be returned.
        after_load_func_async (callable, optional): A function to execute after the page has loaded, for additional interactions.
        table_attr_filter (dict[str, str], optional): A dictionary of attribute name and values to filter the table.
            For example, {"id": "event-content"} to find a table with id="event-content".
        proxies (list[str], optional): Optional list http proxies.

    Returns:
        DataFrame: A Pandas DataFrame containing the data table extracted from the webpage.
    """
    # fetch the webpage content
    logger.info("Fetching data from '%s'...", url)
    html_content = await fetch_webpage_content_playwright(
        url,
        after_load_func_async=after_load_func_async,
        proxies=proxies,
    )
    if not html_content:
        logger.error("Failed to fetch content from '%s'.", url)
        return pd.DataFrame()

    # parse the HTML content and extract the data table
    logger.info("Extracting data table from the fetched content...")
    data_table_df = extract_data_table_from_html(
        html_content, raw_cell_content=raw_cell_content, table_attr_filter=table_attr_filter
    )

    if data_table_df.empty:
        logger.warning("No data table found in the content from '%s'.", url)

    return data_table_df


def _get_http_proxies() -> list[str] | None:
    """
    Builds the list of HTTP proxy connect strings to use for fetching, based on configuration.

    Returns:
        list[str]: A list of HttpProxy.connect_string values when FinHubProxySettings.fetch_website_via_proxy
            is True and proxies are configured, otherwise None. When HttpProxy.https is 1 the connect string
            scheme is normalized to "https://" instead of "http://".
    """
    if not config.settings_finhub_proxy.fetch_website_via_proxy:
        return None

    http_proxies = config.settings_finhub_proxy.http_proxies
    if not http_proxies:
        return None

    result = []
    for proxy in http_proxies:
        connect_string = (
            proxy.connect_string.replace("http://", "https://") if proxy.https == 1 else proxy.connect_string
        )
        result.append(connect_string)
    return result


async def scrape_dividends_from_tipranks(
    url_template: str,
    end_date: datetime.date = datetime.date.today() + datetime.timedelta(days=1),
    tz_name: str = "UTC",
    *,
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

    Returns:
        DataFrame: A Pandas DataFrame containing the data table extracted from the webpage.
    """
    start_date = datetime.datetime.now(ZoneInfo(tz_name)).date()

    # go back 2 working days
    for _ in range(2):
        start_date -= datetime.timedelta(days=1)
        # if weekend, go back to the previous Friday
        if start_date.weekday() >= 5:  # Saturday or Sunday
            start_date -= datetime.timedelta(days=start_date.weekday() - 4)

    proxies = _get_http_proxies()
    final_df = pd.DataFrame()
    while start_date <= end_date:
        if start_date.weekday() >= 5:  # skip if weekend
            start_date += datetime.timedelta(days=1)
            continue

        target_url = url_template.format(date=start_date.strftime("%Y-%m-%d"))
        df = (
            await scrape_data_table_playwright(target_url, after_load_func_async=after_load_func_async, proxies=proxies)
            if use_playwright
            else await scrape_data_table(target_url, proxies=proxies)
        )
        if not df.empty:
            # add column "Ex-Dividend Date" and fill it with the current date
            df["Ex-Dividend Date"] = start_date.strftime("%Y-%m-%d")
            final_df = pd.concat([final_df, df], ignore_index=True)

        # delay randomly a few seconds to avoid overwhelming the server
        delay_seconds = random.uniform(1.00, 3.00)
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
    end_date: datetime.date = datetime.date.today() + datetime.timedelta(days=1),
    tz_name: str = "UTC",
    *,
    after_load_func_async=None,
) -> pd.DataFrame:
    """
    Scrapes dividend data from the TipRanks website for a given URL template and end date, using Playwright.

    Args:
        url_template (str): The URL template for scraping data, with a placeholder for the date (e.g., "https://www.tipranks.com/calendars/dividends/{date}").
        after_load_func_async (callable, optional): A function to execute after the page has loaded, for additional interactions.
        end_date (datetime.date): The end date for scraping data. The function will scrape data from the current date up to this end date.
        tz_name (str): The name of the timezone to use for date calculations (e.g., "Australia/Sydney").

    Returns:
        DataFrame: A Pandas DataFrame containing the data table extracted from the webpage.
    """
    return await scrape_dividends_from_tipranks(
        url_template, end_date, tz_name, use_playwright=True, after_load_func_async=after_load_func_async
    )


async def scrape_dividends_asx(end_date: datetime.date) -> pd.DataFrame:
    """
    Scrapes dividend data from the TipRanks website for Australian stocks.

    Args:
        end_date (datetime.date): The end date for scraping data. The function will scrape data from the current date up to this end date.

    Returns:
        DataFrame: A Pandas DataFrame containing the data table extracted from the webpage.
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


async def scrape_dividends_us(end_date: datetime.date) -> pd.DataFrame:
    """
    Scrapes dividend data from the MarketBeat website for US stocks.

    Args:
        end_date (datetime.date): The end date for scraping data. The function will scrape data from the current date up to this end date.

    Returns:
        DataFrame: A Pandas DataFrame containing the data table extracted from the webpage.
    """
    url_template = "https://www.tipranks.com/calendars/dividends/{date}"
    tz = "America/New_York"
    return await scrape_dividends_from_tipranks_playwright(
        url_template, end_date, tz, after_load_func_async=tipranks_after_load_func
    )


async def scrape_dividends_vn(end_date: datetime.date) -> pd.DataFrame:
    """
    Scrapes dividend data from the VietStock website for VN stocks.

    Args:
        end_date (datetime.date): The end date for scraping data. The function will scrape data from the current date up to this end date.

    Returns:
        DataFrame: A Pandas DataFrame containing the data table extracted from the webpage.
    """

    async def wait_for_page_render_after_load_func(*args, **kwargs):
        import asyncio

        await asyncio.sleep(1.5)

    url_template = "https://finance.vietstock.vn/lich-su-kien.htm?from={s_date}&to={e_date}&page={page}&tab=1&group=13"
    tz_name = "Asia/Ho_Chi_Minh"
    start_date = datetime.datetime.now(ZoneInfo(tz_name)).date()

    # go back 2 working days
    for _ in range(2):
        start_date -= datetime.timedelta(days=1)
        # if weekend, go back to the previous Friday
        if start_date.weekday() >= 5:  # Saturday or Sunday
            start_date -= datetime.timedelta(days=start_date.weekday() - 4)

    proxies = _get_http_proxies()
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
        df = await scrape_data_table_playwright(
            target_url,
            table_attr_filter={"id": "event-content"},
            after_load_func_async=wait_for_page_render_after_load_func,
            proxies=proxies,
        )
        if df.empty or len(df.columns) < 2:
            break
        final_df = pd.concat([final_df, df], ignore_index=True)

        # delay randomly a few seconds to avoid overwhelming the server
        delay_seconds = random.uniform(1.00, 3.00)
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

    proxies = _get_http_proxies()
    final_df = pd.DataFrame()
    while start_date <= end_date:
        if start_date.weekday() >= 5:  # skip if weekend
            start_date += datetime.timedelta(days=1)
            continue

        target_url = url_template.format(date=start_date.strftime("%Y-%m-%d"))
        df = (
            await scrape_data_table_playwright(target_url, after_load_func_async=after_load_func_async, proxies=proxies)
            if use_playwright
            else await scrape_data_table(target_url, proxies=proxies)
        )
        if not df.empty:
            # add column "Announcement Date" and fill it with the current date
            df["Announcement Date"] = start_date.strftime("%Y-%m-%d")
            final_df = pd.concat([final_df, df], ignore_index=True)

        # delay randomly a few seconds to avoid overwhelming the server
        delay_seconds = random.uniform(1.00, 3.00)
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
