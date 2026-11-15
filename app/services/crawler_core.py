import asyncio
import logging
import random
import time

import bs4
import cloudscraper
import pandas as pd
import starlette.concurrency
from playwright import async_api as playwright_async_api
from playwright.async_api import Browser

from ..utils import cache

logger = logging.getLogger(__name__)

_HTML_CACHE_TTL = 24 * 60 * 60


def _callback_name(callback) -> str:
    if not callback:
        return ""
    return f"{getattr(callback, '__module__', '')}.{getattr(callback, '__qualname__', type(callback).__qualname__)}"


def extract_data_table_from_html(
    html_content: str, *, raw_cell_content=False, table_attr_filter=None, filter_skip=0
) -> pd.DataFrame:
    """
    Extracts data from the given HTML content, assuming main content is in a table, and returns it as a Pandas DataFrame.

    Args:
        html_content (str): The HTML content to parse.
        raw_cell_content (bool, optional): If False, cell content will be cleaned-up; otherwise cell's raw content will be returned.
        table_attr_filter (dict[str, str], optional): A dictionary of attribute name and values to filter the table.
            For example, {"id": "event-content"} to find a table with id="event-content".
        filter_skip (int, optional): The number of tables that match the filter to skip.
            This is useful when there are multiple tables on the page and you want to select a specific one.

    Returns:
        DataFrame: A Pandas DataFrame containing the extracted data.
    """
    soup = bs4.BeautifulSoup(html_content, "html.parser")

    # Find the main data table(s), skip first `filter_skip` tables that match the filter
    tables = soup.find_all("table", attrs=table_attr_filter)
    if len(tables) <= filter_skip:
        return pd.DataFrame()
    table = tables[filter_skip]

    # 1. Extract the table headers
    # headers_list = None
    thead = table.find("thead")
    if thead:
        headers_list = [th.text.strip() for th in thead.find_all("th")]
        if len(headers_list) == 0:
            # fallback to <td> if no <th> found in <thead>
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
    url: str, *, retries: int = 3, backoff_factor: float = 0.5, cache_ttl: int = _HTML_CACHE_TTL
) -> str | None:
    """
    Fetches the content of a webpage, retrying failures except HTTP client errors (400-499).

    Args:
        url (str): The URL of the webpage to fetch.
        retries (int, optional): Number of times to retry the request in case of failure. Defaults to 3.
        backoff_factor (float, optional): Factor for calculating sleep time between retries. Defaults to 0.5.
        cache_ttl (int, optional): Lifetime of cached HTML, in seconds. Defaults to 24 hours.

    Returns:
        str: The content of the webpage if successful, otherwise None.
    """
    cache_key = cache.generate_key("crawler", "http", url, *([str(cache_ttl)] if cache_ttl != _HTML_CACHE_TTL else []))
    cached_content = await cache.get(cache_key)
    if cached_content is not None:
        logger.info("Using cached content for '%s'.", url)
        return cached_content

    scraper = cloudscraper.create_scraper(browser={"browser": "chrome", "platform": "windows", "desktop": True})
    start_time = time.monotonic()
    for attempt in range(retries):
        try:
            response = await starlette.concurrency.run_in_threadpool(scraper.get, url, timeout=60)
            if 400 <= response.status_code < 500:
                logger.warning("Client error HTTP %s fetching URL: %s. Not retrying.", response.status_code, url)
                return None
            response.raise_for_status()  # Raise an exception for HTTP errors
            await cache.set(cache_key, response.text, ttl=cache_ttl)
            logger.info("Fetched content from '%s' in %.2f seconds.", url, time.monotonic() - start_time)
            return response.text
        except Exception as e:
            logger.warning(f"Fetching attempt {attempt + 1} failed for URL: {url}. Error: {e}")
            if attempt < retries - 1:
                sleep_time = backoff_factor * (2**attempt) + random.uniform(0, 0.1)  # Exponential backoff
                logger.info(f"Retrying after {float(sleep_time):.2f} seconds...")
                await asyncio.sleep(sleep_time)
    logger.error(f"All {retries} fetching attempts failed for URL: {url}.")
    return None


async def fetch_webpage_content_playwright(
    url: str,
    *,
    after_load_func_async=None,
    retries: int = 2,
    backoff_factor: float = 0.5,
    cache_ttl: int = _HTML_CACHE_TTL,
) -> str | None:
    """
    Fetches webpage content using Playwright, retrying failures except HTTP client errors (400-499).

    Args:
        url (str): The URL of the webpage to fetch.
        after_load_func_async (callable, optional): A function to execute after the page has loaded, for additional interactions.
        retries (int, optional): Number of times to retry the request in case of failure. Defaults to 2.
        backoff_factor (float, optional): Factor for calculating sleep time between retries. Defaults to 0.5.
        cache_ttl (int, optional): Lifetime of cached HTML, in seconds. Defaults to 24 hours.

    Returns:
        str: The content of the webpage if successful, otherwise None.
    """
    cache_key = cache.generate_key(
        "crawler",
        "playwright",
        _callback_name(after_load_func_async),
        url,
        *([str(cache_ttl)] if cache_ttl != _HTML_CACHE_TTL else []),
    )
    cached_content = await cache.get(cache_key)
    if cached_content is not None:
        logger.info("Using cached Playwright content for '%s'.", url)
        return cached_content

    start_time = time.monotonic()
    for attempt in range(retries):
        try:
            async with playwright_async_api.async_playwright() as p:
                browser = await p.webkit.launch(headless=True)
                try:
                    page = await browser.new_page(
                        screen=playwright_async_api.ViewportSize(width=1664, height=1110),
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36 Edg/145.0.0.0",
                    )
                    response = await page.goto(url, timeout=60000)
                    if response is None:
                        raise RuntimeError("Navigation returned no HTTP response")
                    if 400 <= response.status < 500:
                        logger.warning("Client error HTTP %s fetching URL: %s. Not retrying.", response.status, url)
                        return None
                    if response.status >= 500:
                        raise RuntimeError(f"HTTP {response.status} fetching URL: {url}")
                    if after_load_func_async:
                        await after_load_func_async(page)
                    page_content = await page.content()
                finally:
                    await browser.close()
                await cache.set(cache_key, page_content, ttl=cache_ttl)
                logger.info("Fetched content from '%s' in %.2f seconds.", url, time.monotonic() - start_time)
                return page_content
        except Exception as e:
            logger.warning(f"Playwright fetching attempt {attempt + 1} failed for URL: {url}. Error: {e}")
            if attempt < retries - 1:
                sleep_time = backoff_factor * (2**attempt) + random.uniform(0, 0.1)  # Exponential backoff
                logger.info(f"Retrying after {float(sleep_time):.2f} seconds...")
                await asyncio.sleep(sleep_time)
    logger.error(f"All {retries} Playwright fetching attempts failed for URL: {url}.")
    return None


async def fetch_multi_webpages_content_playwright(
    urls: list[str],
    *,
    after_load_func_async=None,
    delay_between_requests: float = 0.0,
    cache_ttl: int = _HTML_CACHE_TTL,
) -> list[str | None]:
    """
    Fetches multiple webpages content using Playwright concurrently, retrying failures except HTTP client errors (400-499).

    Args:
        urls (list[str]): A list of URLs of the webpages to fetch.
        after_load_func_async (callable, optional): A function to execute after each page has loaded, for additional interactions.
        delay_between_requests (float, optional): Delay between requests in seconds. Defaults to 0.0.
        cache_ttl (int, optional): Lifetime of cached HTML, in seconds. Defaults to 24 hours.
    Returns:
        list[str | None]: A list of webpage contents corresponding to the input URLs. Each entry is the content of the webpage if successful, otherwise None.
    """

    async def _check_cached_content(url: str) -> str | None:
        cache_key = cache.generate_key(
            "crawler",
            "playwright",
            _callback_name(after_load_func_async),
            url,
            *([str(cache_ttl)] if cache_ttl != _HTML_CACHE_TTL else []),
        )
        return await cache.get(cache_key)

    async def _set_cached_content(url: str, page_content: str) -> None:
        cache_key = cache.generate_key(
            "crawler",
            "playwright",
            _callback_name(after_load_func_async),
            url,
            *([str(cache_ttl)] if cache_ttl != _HTML_CACHE_TTL else []),
        )
        await cache.set(cache_key, page_content, ttl=cache_ttl)

    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36 Edg/145.0.0.0"

    async def _fetch_single_page(browser: Browser, url: str) -> str | None:
        cached_content = await _check_cached_content(url)
        if cached_content is not None:
            logger.info("Using cached Playwright content for '%s'.", url)
            return cached_content

        start_time = time.monotonic()
        try:
            page = await browser.new_page(
                screen=playwright_async_api.ViewportSize(width=1664, height=1110),
                user_agent=user_agent,
            )
            response = await page.goto(url, timeout=60000)
            if response is None:
                raise RuntimeError("Navigation returned no HTTP response")

            if 200 <= response.status < 300:
                if after_load_func_async:
                    await after_load_func_async(page)
                page_content = await page.content()
                await _set_cached_content(url, page_content)
                logger.info("Fetched content from '%s' in %.2f seconds.", url, time.monotonic() - start_time)
                return page_content

            raise RuntimeError(f"HTTP {response.status} fetching URL: {url}")
        except Exception as e:
            logger.error(f"Failed to create a new page for URL: {url}. Error: {e}")
            return None

    result = []

    async with playwright_async_api.async_playwright() as p:
        browser = await p.webkit.launch(headless=True)
        try:
            for url in urls:
                page_content = await _fetch_single_page(browser, url)
                result.append(page_content if page_content else None)
                if delay_between_requests > 0:
                    await asyncio.sleep(delay_between_requests)
        finally:
            await browser.close()

    return result


async def fetch_webpage_content_fallback_to_playwright(url: str, *, cache_ttl: int = _HTML_CACHE_TTL) -> str | None:
    """Fetches webpage content over HTTP with up to two attempts, falling back to Playwright on failure."""
    content = await fetch_webpage_content(url, retries=2, cache_ttl=cache_ttl)
    if content is not None:
        return content
    return await fetch_webpage_content_playwright(url, retries=2, cache_ttl=cache_ttl)


async def scrape_data_table(url: str, *, raw_cell_content=False, table_attr_filter=None, filter_skip=0) -> pd.DataFrame:
    """
    Scrapes data from the given URL, assuming main content is in a table, and returns it as a Pandas DataFrame.

    Args:
        url (str): The URL of the webpage containing the data table to scrape.
        raw_cell_content (bool, optional): If False, cell content will be cleaned-up; otherwise cell's raw content will be returned.
        table_attr_filter (dict[str, str], optional): A dictionary of attribute name and values to filter the table.
            For example, {"id": "event-content"} to find a table with id="event-content".
        filter_skip (int, optional): The number of tables that match the filter to skip.
            This is useful when there are multiple tables on the page and you want to select a specific one.

    Returns:
        DataFrame: A Pandas DataFrame containing the data table extracted from the webpage.
    """
    # fetch the webpage content
    logger.info("Fetching data from '%s'...", url)
    html_content = await fetch_webpage_content_fallback_to_playwright(url)
    if not html_content:
        logger.error("Failed to fetch content from '%s'.", url)
        return pd.DataFrame()

    # parse the HTML content and extract the data table
    logger.info("Extracting data table from the fetched content...")
    data_table_df = extract_data_table_from_html(
        html_content, raw_cell_content=raw_cell_content, table_attr_filter=table_attr_filter, filter_skip=filter_skip
    )

    if data_table_df.empty:
        logger.warning("No data table found in the content from '%s'.", url)

    return data_table_df


async def scrape_data_table_playwright(
    url: str, *, raw_cell_content=False, after_load_func_async=None, table_attr_filter=None, filter_skip=0
) -> pd.DataFrame:
    """
    Scrapes data from the given URL using Playwright, assuming main content is in a table, and returns it as a Pandas DataFrame.

    Args:
        url (str): The URL of the webpage containing the data table to scrape.
        raw_cell_content (bool, optional): If False, cell content will be cleaned-up; otherwise cell's raw content will be returned.
        after_load_func_async (callable, optional): A function to execute after the page has loaded, for additional interactions.
        table_attr_filter (dict[str, str], optional): A dictionary of attribute name and values to filter the table.
            For example, {"id": "event-content"} to find a table with id="event-content".
        filter_skip (int, optional): The number of tables that match the filter to skip.
            This is useful when there are multiple tables on the page and you want to select a specific one.

    Returns:
        DataFrame: A Pandas DataFrame containing the data table extracted from the webpage.
    """
    # fetch the webpage content
    logger.info("Fetching data from '%s'...", url)
    html_content = await fetch_webpage_content_playwright(
        url,
        after_load_func_async=after_load_func_async,
    )
    if not html_content:
        logger.error("Failed to fetch content from '%s'.", url)
        return pd.DataFrame()

    # parse the HTML content and extract the data table
    logger.info("Extracting data table from the fetched content...")
    data_table_df = extract_data_table_from_html(
        html_content, raw_cell_content=raw_cell_content, table_attr_filter=table_attr_filter, filter_skip=filter_skip
    )

    if data_table_df.empty:
        logger.warning("No data table found in the content from '%s'.", url)

    return data_table_df
