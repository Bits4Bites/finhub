import asyncio
import datetime
import random
import zoneinfo

import pandas as pd

from . import crawler_core, market


async def _scrape_dividends_from_tipranks(
    url_template: str,
    *,
    tz_name: str = "UTC",
    tz_info: zoneinfo.ZoneInfo | None = None,
    end_date: datetime.date | None = None,
) -> pd.DataFrame:
    """
    Scrapes dividend data from the TipRanks website for a given URL.

    Args:
        url_template (str): The URL template of the TipRanks dividends calendar page. It must contain a {date} placeholder for the date in "yyyy-MM-dd" format.
        tz_name (str, optional): The name of the timezone to use for date calculations (e.g., "Australia/Sydney").
        tz_info (zoneinfo.ZoneInfo, optional): A timezone object to use for date calculations. If provided, it will override tz_name.
        end_date (datetime.date, optional): The end date for scraping data. The function will scrape data from the current date up to this end date. If not provided, the function will scrape all available data.
    Returns:
        DataFrame: A Pandas DataFrame containing the data table extracted from the webpage, with the following columns:
            - "Ex-Div Date": The ex-dividend date of the dividend event, in format "yyyy-MM-dd".
            - "Ticker": The stock ticker symbol (e.g. AAPL).
            - "Company": The name of the company (e.g. Apple Inc.).
            - "Div Amount": The dividend amount per share, as numeric value (e.g. 1.5).
            - "Div Yield": (optional) The dividend yield of the dividend amount (value 0.0477 means 4.77%).
            - "Market Cap": (optional) The market capitalization of the company, as numeric value (e.g. 2500000000).
            - "Payment Date": (optional) The payment date of the dividend event, in format "yyyy-MM-dd"
    """
    tz_info = tz_info if tz_info else zoneinfo.ZoneInfo(tz_name)
    urls = []
    dates = []
    current_date = datetime.datetime.now(tz_info).date()
    while current_date <= end_date:
        urls.append(url_template.format(date=current_date.strftime("%Y-%m-%d")))
        dates.append(current_date.strftime("%Y-%m-%d"))
        current_date += datetime.timedelta(days=1)
    page_content_list = await crawler_core.fetch_multi_webpages_content_playwright(
        urls,
        delay_between_requests=1.0,
    )
    df = pd.DataFrame()
    for index, page_content in enumerate(page_content_list):
        if page_content is None:
            continue
        page_df = crawler_core.extract_data_table_from_html(page_content)
        page_df["Ex-Div Date"] = dates[index]
        # values in column "Payment Date" are either "In x Days" or "Next Month"
        # if "Next Month", we consider it's "In 30 days"
        # we extract the number of days from the string and add it to the "Ex-Div Date" to get the "Payment Date"
        if "Payment Date" in page_df.columns:
            # first replace "Next Month" with "In 30 Days"
            page_df["Payment Date"] = page_df["Payment Date"].replace("Next Month", "In 30 Days")
            # then convert the "Payment Date" to a date by adding the number of days to the "Ex-Div Date"
            page_df["Payment Date"] = page_df["Payment Date"].apply(
                lambda x: (
                    (
                        datetime.datetime.strptime(dates[index], "%Y-%m-%d")
                        + datetime.timedelta(days=int(x.split()[1]))
                    ).strftime("%Y-%m-%d")
                    if isinstance(x, str) and x.startswith("In ")
                    else "N/A"
                )
            )
        # append each page_df to df
        df = pd.concat([df, page_df], ignore_index=True)

    # remove rows that the value of first column is "Currently there are no dividends available for this date."
    df = df[df.iloc[:, 0] != "Currently there are no dividends available for this date."]

    # remove irrelevant columns
    cols_to_remove = ["Analyst Consensus", "Smart Score", "Payout Ratio", "Follow"]
    df = df.drop(columns=cols_to_remove, errors="ignore")

    # rename column "Name" to "Ticker"
    df = df.rename(columns={"Name": "Ticker"})
    # rename column "Dividend Yield" to "Div Yield"
    df = df.rename(columns={"Dividend Yield": "Div Yield"})
    # rename column "Dividend Amount" to "Div Amount"
    df = df.rename(columns={"Dividend Amount": "Div Amount"})

    # values in column "Div Yield" are in format "4.77%", convert to numeric value (4.77% -> 0.0477)
    df["Div Yield"] = df["Div Yield"].str.rstrip("%").astype(float) / 100
    # value in column "Div Amount" are in format "$1.5", convert to numeric value (remove $ and convert to float)
    df["Div Amount"] = df["Div Amount"].str.replace("$", "", regex=False).astype(float)
    # value in column "Market Cap" are in format "$2.5B", convert to numeric value:
    # - remove $ and convert to int, T -> *1e12, B -> *1e9, M -> *1e6, K -> *1e3
    # - otherwise, set to 0 if not a valid number
    df["Market Cap"] = df["Market Cap"].str.replace("$", "", regex=False).astype(str)
    df["Market Cap"] = df["Market Cap"].apply(
        lambda x: int(
            float(x[:-1]) * 1e12
            if x.endswith("T")
            else float(x[:-1]) * 1e9
            if x.endswith("B")
            else float(x[:-1]) * 1e6
            if x.endswith("M")
            else float(x[:-1]) * 1e3
            if x.endswith("K")
            else float(x)
        )
    )

    return df


async def scrape_dividends_asx(end_date: datetime.date) -> pd.DataFrame:
    """
    Scrapes dividend data for Australian stocks.

    Args:
        end_date (datetime.date): The end date for scraping data. The function will scrape data from the current date up to this end date.

    Returns:
        DataFrame: A Pandas DataFrame containing the data table extracted from the webpage, with the following columns:
            - "Ex-Div Date": The ex-dividend date of the dividend event, in format "yyyy-MM-dd".
            - "Ticker": The stock ticker symbol (e.g. CBA).
            - "Company": The name of the company (e.g. Commonwealth Bank of Australia).
            - "Div Amount": The dividend amount per share, as numeric value (e.g. 1.5).
            - "Div Yield": (optional) The dividend yield of the dividend amount (value 0.0477 means 4.77%).
            - "Market Cap": (optional) The market capitalization of the company, as numeric value (e.g. 2500000000).
            - "Payment Date": (optional) The payment date of the dividend event, in format "yyyy-MM-dd"
            - "Exchange": The exchange where the stock is listed, set to "ASX".
            - "Currency": The currency of the dividend amount, set to "AUD".
    """
    url_template = "https://www.tipranks.com/calendars/dividends/{date}/australia"
    tz = "Australia/Sydney"
    df = await _scrape_dividends_from_tipranks(url_template, tz_name=tz, end_date=end_date)

    urls = []
    current_date = datetime.datetime.now(zoneinfo.ZoneInfo(tz)).date()
    while current_date <= end_date:
        urls.append(url_template.format(date=current_date.strftime("%Y-%m-%d")))
        current_date += datetime.timedelta(days=1)

    # before returning result:
    # - add column "Exchange" with value "ASX"
    # - add column "Currency" with value "AUD"
    df["Exchange"] = "ASX"
    df["Currency"] = "AUD"

    return df


async def scrape_dividends_us(end_date: datetime.date) -> pd.DataFrame:
    """
    Scrapes dividend data for US stocks.

    Args:
        end_date (datetime.date): The end date for scraping data. The function will scrape data from the current date up to this end date.

    Returns:
        DataFrame: A Pandas DataFrame containing the data table extracted from the webpage, with the following columns:
            - "Ex-Div Date": The ex-dividend date of the dividend event, in format "yyyy-MM-dd".
            - "Ticker": The stock ticker symbol (e.g. AAPL).
            - "Company": The name of the company (e.g. Apple Inc.).
            - "Div Amount": The dividend amount per share, as numeric value (e.g. 1.5).
            - "Div Yield": (optional) The dividend yield of the dividend amount (value 0.0477 means 4.77%).
            - "Market Cap": (optional) The market capitalization of the company, as numeric value (e.g. 2500000000).
            - "Payment Date": (optional) The payment date of the dividend event, in format "yyyy-MM-dd"
            - "Exchange": The exchange where the stock is listed.
            - "Currency": The currency of the dividend amount, set to "USD".
    """
    url_template = "https://www.tipranks.com/calendars/dividends/{date}"
    tz = "America/New_York"
    df = await _scrape_dividends_from_tipranks(url_template, tz_name=tz, end_date=end_date)

    urls = []
    current_date = datetime.datetime.now(zoneinfo.ZoneInfo(tz)).date()
    while current_date <= end_date:
        urls.append(url_template.format(date=current_date.strftime("%Y-%m-%d")))
        current_date += datetime.timedelta(days=1)

    # before returning result:
    # - add column "Currency" with value "USD"
    df["Currency"] = "USD"
    # - for column "Exchange", we look up the exchange from market.market_indices.revert_lookup_company("US", ticker)
    #   and get the exchange name from the CompanyBriefInfo object
    df["Exchange"] = df["Ticker"].apply(
        lambda x: (
            market.market_indices.revert_lookup_company("US", x).extract_exchange_code()[0]
            if market.market_indices.revert_lookup_company("US", x)
            else "N/A"
        )
    )

    return df


async def _wait_for_vietstock_page_render_after_load_func(*args, **kwargs):
    delay_seconds = random.uniform(1.00, 2.00)
    await asyncio.sleep(delay_seconds)


async def _scrape_cash_dividends_vn_vietstock(start_date: datetime.date, end_date: datetime.date) -> pd.DataFrame:
    """
    Scrapes cash dividend data from the VietStock website for VN stocks.

    Args:
        start_date (datetime.date): The start date for scraping data. The function will scrape data from start_date to end_date.
        end_date (datetime.date): The end date for scraping data. The function will scrape data from start_date to end_date.
    Returns:
        DataFrame: A Pandas DataFrame containing the data table extracted from the webpage, with the following columns:
            - "event_category": The category of the event, set to "dividend".
            - "Ex-Div Date": The ex-dividend date of the dividend event, in format "yyyy-MM-dd".
            - "Ticker": The stock ticker symbol (e.g. ACB).
            - "Company": The name of the company (currently set to Ticker value).
            - "Div Amount": The dividend amount per share, as numeric value (e.g. 1500).
            - "Div Yield": (optional) The dividend yield of the dividend amount (value 0.15 means 15%).
            - "Payment Date": (optional) The payment date of the dividend event, in format "yyyy-MM-dd"
            - "Exchange": The exchange where the stock is listed.
            - "Currency": The currency of the dividend amount, set to "VND".
    """
    url_template = "https://finance.vietstock.vn/lich-su-kien.htm?from={s_date}&to={e_date}&page={page}&tab=1&group=13"
    final_df = pd.DataFrame()
    page = 1
    while True:
        target_url = url_template.format(
            s_date=start_date.strftime("%Y-%m-%d"),
            e_date=end_date.strftime("%Y-%m-%d"),
            page=page,
        )
        df = await crawler_core.scrape_data_table_playwright(
            target_url,
            table_attr_filter={"id": "event-content"},
            after_load_func_async=_wait_for_vietstock_page_render_after_load_func,
        )
        if df.empty or len(df.columns) < 2:
            break

        final_df = pd.concat([final_df, df], ignore_index=True)

        # delay randomly a few seconds to avoid overwhelming the server
        delay_seconds = random.uniform(1.00, 3.00)
        await asyncio.sleep(delay_seconds)

        page += 1

    # remove non-essential columns: "STT", "Nội dung sự kiện", "Ngày ĐKCC"
    cols_to_drop = ["STT", "Nội dung sự kiện", "Ngày ĐKCC"]
    for col in cols_to_drop:
        if col in final_df.columns:
            final_df = final_df.drop(columns=[col])

    # rename columns:
    # - "Mã CK" to "Ticker"
    # - "Sàn" to "Exchange"
    # - "Ngày GDKHQ▼" to "Ex-Div Date"
    # - "Ngày thực hiện" to "Payment Date"
    # - "Tỷ lệ" to "Div Yield"
    rename_map = {
        "Mã CK": "Ticker",
        "Sàn": "Exchange",
        "Ngày GDKHQ▼": "Ex-Div Date",
        "Ngày thực hiện": "Payment Date",
        "Tỷ lệ": "Div Yield",
    }
    for old_col, new_col in rename_map.items():
        final_df = final_df.rename(columns={old_col: new_col})

    # Upper case column "Exchange"
    final_df["Exchange"] = final_df["Exchange"].str.upper()
    # "Ex-Div Date" and "Payment Date" are in format "dd/MM/yyyy", convert to "yyyy-MM-dd"
    for date_col in ["Ex-Div Date", "Payment Date"]:
        final_df[date_col] = pd.to_datetime(final_df[date_col], format="%d/%m/%Y").dt.strftime("%Y-%m-%d")

    # values in column "Div Yield" are in format "15%", convert to numeric value (15% -> 0.15)
    final_df["Div Yield"] = final_df["Div Yield"].str.rstrip("%").astype(float) / 100

    # - add column "event_category" with value "dividend"
    final_df["event_category"] = "dividend"
    # - add column "Company" with value same as "Ticker"
    final_df["Company"] = final_df["Ticker"]
    # - add column "Div Amount" = 10000 * "Div Yield" (as numeric value)
    final_df["Div Amount"] = final_df["Div Yield"] * 10000
    # - add column "Currency" with value "VND"
    final_df["Currency"] = "VND"

    return final_df


async def scrape_dividends_vn(end_date: datetime.date) -> pd.DataFrame:
    """
    Scrapes dividend data from the VietStock website for VN stocks.

    Args:
        end_date (datetime.date): The end date for scraping data. The function will scrape data from the current date up to this end date.

    Returns:
        DataFrame: A Pandas DataFrame containing the data table extracted from the webpage, with the following columns:
            - "event_category": The category of the event, either "dividend", "stock dividend" or "stock bonus"
            - "Ex-Div Date": The ex-dividend date of the dividend event, in format "yyyy-MM-dd".
            - "Ticker": The stock ticker symbol (e.g. ACB).
            - "Company": The name of the company (currently set to Ticker value).
            - "Div Amount": The dividend amount per share, as numeric value (e.g. 1500).
            - "Div Yield": (optional) The dividend yield of the dividend amount (value 0.15 means 15%).
            - "Payment Date": (optional) The payment date of the dividend event, in format "yyyy-MM-dd"
            - "Exchange": The exchange where the stock is listed.
            - "Currency": The currency of the dividend amount, set to "VND".
    """
    tz_name = "Asia/Ho_Chi_Minh"
    start_date = datetime.datetime.now(zoneinfo.ZoneInfo(tz_name)).date()
    # go back 2 working days
    for _ in range(2):
        start_date -= datetime.timedelta(days=1)
        # if weekend, go back to the previous Friday
        if start_date.weekday() >= 5:  # Saturday or Sunday
            start_date -= datetime.timedelta(days=start_date.weekday() - 4)

    final_df = pd.DataFrame()
    df_dividend = await _scrape_cash_dividends_vn_vietstock(start_date, end_date)
    final_df = pd.concat([final_df, df_dividend], ignore_index=True)

    return final_df
