import datetime
import logging
import random
import time
from zoneinfo import ZoneInfo
import cloudscraper
from bs4 import BeautifulSoup
import pandas as pd


def scrape_data_table(url: str) -> pd.DataFrame:
    """
    Scrapes data from the given URL, assuming main content is in a table, and returns it as a Pandas DataFrame.

    Args:
        url (str): The URL of the webpage containing the data table to scrape.
    """

    logging.info("Fetching data from '%s'...", url)

    scraper = cloudscraper.create_scraper()
    response = scraper.get(url)

    # Check if the request was successful
    if response.status_code != 200:
        logging.error("Failed to fetch data from '%s', status code: '%d'.", url, response.status_code)
        return pd.DataFrame()

    # Parse the HTML content
    soup = BeautifulSoup(response.text, "html.parser")

    # Find the main dividend table (usually the first table on the page)
    table = soup.find("table")

    if not table:
        logging.error("Could not find the data table on '%s'.", url)
        return pd.DataFrame()

    # 1. Extract the table headers (Code, Ex-Div, Amount, etc.)
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
        logging.warning("No data rows found in the table on '%s'.", url)
        return pd.DataFrame()

    # 3. Create a Pandas DataFrame for neat formatting
    # Note: Sometimes the website has a hidden column for mobile views.
    # We slice data/headers to match lengths just in case.
    min_length = min(len(headers_list), len(data[0]))
    headers_list = headers_list[:min_length]
    data = [row[:min_length] for row in data]

    df = pd.DataFrame(data, columns=headers_list)
    return df


def scrape_dividends_from_tipranks(url_template: str, end_date: datetime.date, tz_name: str) -> pd.DataFrame:
    """
    Scrapes dividend data from the TipRanks website for a given URL template and end date.

    Args:
        url_template (str): The URL template for scraping data, with a placeholder for the date (e.g., "https://www.tipranks.com/calendars/dividends/{date}").
        end_date (datetime.date): The end date for scraping data. The function will scrape data from the current date up to this end date.
        tz_name (str): The name of the timezone to use for date calculations (e.g., "Australia/Sydney").
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
        df = scrape_data_table(target_url)
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


def scrape_dividends_asx(end_date: datetime.date) -> pd.DataFrame:
    """
    Scrapes dividend data from the TipRanks website for Australian stocks.

    Args:
        end_date (datetime.date): The end date for scraping data. The function will scrape data from the current date up to this end date.
    """
    url_template = "https://www.tipranks.com/calendars/dividends/{date}/australia"
    return scrape_dividends_from_tipranks(url_template, end_date, "Australia/Sydney")


def scrape_dividends_us(end_date: datetime.date) -> pd.DataFrame:
    """
    Scrapes dividend data from the MarketBeat website for US stocks.

    Args:
        end_date (datetime.date): The end date for scraping data. The function will scrape data from the current date up to this end date.
    """
    url_template = "https://www.tipranks.com/calendars/dividends/{date}"
    return scrape_dividends_from_tipranks(url_template, end_date, "America/New_York")


def scrape_earnings_from_tipranks(url_template: str, end_date: datetime.date, tz_name: str) -> pd.DataFrame:
    """
    Scrapes earnings announcement data from a given URL template and end date.

    Args:
        url_template (str): The URL template for scraping data, with a placeholder for the date (e.g., "https://www.tipranks.com/calendars/earnings/{date}").
        end_date (datetime.date): The end date for scraping data. The function will scrape data from the current date up to this end date.
        tz_name (str): The name of the timezone to use for date calculations (e.g., "Australia/Sydney").
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
        df = scrape_data_table(target_url)
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


def scrape_earnings_asx(end_date: datetime.date) -> pd.DataFrame:
    """
    Scrapes earnings announcement data from the TipRanks website for Australian stocks.

    Args:
        end_date (datetime.date): The end date for scraping data. The function will scrape data from the current date up to this end date.
    """
    url_template = "https://www.tipranks.com/calendars/earnings/{date}/australia"
    return scrape_earnings_from_tipranks(url_template, end_date, "Australia/Sydney")


def scrape_earnings_us(end_date: datetime.date) -> pd.DataFrame:
    """
    Scrapes earnings announcement data from the TipRanks website for US stocks.

    Args:
        end_date (datetime.date): The end date for scraping data. The function will scrape data from the current date up to this end date.
    """
    url_template = "https://www.tipranks.com/calendars/earnings/{date}"
    return scrape_earnings_from_tipranks(url_template, end_date, "America/New_York")
