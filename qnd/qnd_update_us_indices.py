# Run with the following command from the parent company:
# $ python -m qnd.qnd_update_us_indices

import asyncio
import json
from datetime import datetime

from app.services import crawler as crawler_service

async def update_us_index(index: str, num_check: int):
    url = None
    table_attr_filter = None
    raw_cell_content = False
    symbol_prefix = ""
    to_file = None
    columns_to_drop = [
        "#",
        "Price",
        "Market Cap",
        "Revenue",
        "Net Income",
        "EPS",
        "Volume",
        "GICS Sub-Industry",
        "Headquarters Location",
        "Date added",
        "CIK",
        "Founded",
        "SEC filings",
    ]
    columns_remap = {
        "Symbol": "symbol",
        "Company Name": "company",
        "Sector": "sector",
        "Security": "company",
        "GICS Sector": "sector",
    }
    index = index.upper()
    match index:
        case "NASDAQ100" | "NASDAQ 100" | "NASDAQ-100":
            url = "https://finspry.com/lists/nasdaq100"
            to_file = "resources/indices/nasdaq100.json"
            symbol_prefix = "NASDAQ:"
        case "SP500" | "SP 500" | "SP-500" | "S&P500" | "S&P 500" | "S&P-500":
            url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
            to_file = "resources/indices/sp500.json"
            table_attr_filter = {"id": "constituents"}
            raw_cell_content = True
        case "SP400" | "SP 400" | "SP-400" | "S&P400" | "S&P 400" | "S&P-400":
            url = "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies"
            to_file = "resources/indices/spmidcap400.json"
            table_attr_filter = {"id": "constituents"}
            raw_cell_content = True
        case "SP600" | "SP 600" | "SP-600" | "S&P600" | "S&P 600" | "S&P-600":
            url = "https://en.wikipedia.org/wiki/List_of_S%26P_600_companies"
            to_file = "resources/indices/spsmallcap600.json"
            table_attr_filter = {"id": "constituents"}
            raw_cell_content = True

    data = await crawler_service.scrape_data_table(url, raw_cell_content=raw_cell_content, table_attr_filter=table_attr_filter)
    if data is None or data.empty:
        raise EnvironmentError(f"No data available from {url}.")
    if len(data) < num_check:
        raise ValueError(f"Expected at least {num_check} entries, but got {len(data)}.")

    # Base transformations
    for col in columns_to_drop:
        if col in data.columns:
            data = data.drop(columns=[col])
    for old_col, new_col in columns_remap.items():
        if old_col in data.columns:
            data = data.rename(columns={old_col: new_col})

    # Specific transformation
    if url.startswith("https://en.wikipedia.org/"):
        data["company"] = data["company"].str.replace(r'<[^>]+>', '', regex=True).str.strip()
        data["exchange"] = data["symbol"].apply(lambda x: "NYSE" if "nyse.com" in x else "NASDAQ" if "nasdaq.com" in x else "ERROR")
        data["symbol"] = data["symbol"].str.extract(r'>([^<]+)<')
        data["symbol"] = data["exchange"] + ":" + data["symbol"]
        data = data.drop(columns=["exchange"])

    if symbol_prefix:
        data["symbol"] = data["symbol"].apply(lambda x: symbol_prefix + x.strip())

    timestamp = datetime.now().strftime("%Y-%m-%d")
    data_obj = data.to_dict(orient="records")
    final_obj = {
        "date": timestamp,
        "data": data_obj,
    }
    json.dump(final_obj, open(to_file, "w"), indent=4)
    print(f"{index} data with {len(data)} rows has been updated and saved to {to_file}.")


async def main():
    await update_us_index("NASDAQ100", 90)
    await update_us_index("SP500", 490)
    await update_us_index("SP400", 380)
    await update_us_index("SP600", 550)


asyncio.run(main())
