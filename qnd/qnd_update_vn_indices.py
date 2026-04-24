# Run with the following command from the parent company:
# $ python -m qnd.qnd_update_vn_indices

import asyncio
import json
from datetime import datetime

from app.services import crawler as crawler_service


def convert_market_cap(market_cap_str):
    market_cap_str = market_cap_str.replace(",", "")
    if market_cap_str.endswith("T"):
        return float(market_cap_str[:-1]) * 1e12
    elif market_cap_str.endswith("B"):
        return float(market_cap_str[:-1]) * 1e9
    elif market_cap_str.endswith("M"):
        return float(market_cap_str[:-1]) * 1e6
    elif market_cap_str.endswith("K"):
        return float(market_cap_str[:-1]) * 1e3
    else:
        return float(market_cap_str)


async def update_vn_index_hose():
    url = "https://stockanalysis.com/list/ho-chi-minh-stock-exchange/"
    data = await crawler_service.scrape_data_table(url, table_attr_filter={"id": "main-table"})

    # data["Market Cap"] is in the format of "1.5B", "300M", etc. We need to convert it to a number for sorting and filtering.
    data["Market Cap"] = data["Market Cap"].apply(convert_market_cap)

    # sort by market cap in descending order
    data = data.sort_values(by="Market Cap", ascending=False)

    columns_to_drop = ["No.", "Stock Price", "% Change", "Revenue"]
    for column in columns_to_drop:
        if column in data.columns:
            data = data.drop(columns=[column])
    columns_remap = {
        "Symbol": "symbol",
        "Company Name": "company",
        "Market Cap": "market_cap",
    }
    for old_col, new_col in columns_remap.items():
        if old_col in data.columns:
            data = data.rename(columns={old_col: new_col})
    data["symbol"] = data["symbol"].apply(lambda x: "HOSE:" + x.strip())
    data["market_cap"] = data["market_cap"].astype(int)

    timestamp = datetime.now().strftime("%Y-%m-%d")

    to_file = "resources/indices/vn30.json"
    data_top30 = data.head(30)
    data_obj = data_top30.to_dict(orient="records")
    final_obj = {
        "date": timestamp,
        "data": data_obj,
    }
    with open(to_file, "w") as f:
        json.dump(final_obj, f, indent=4)
    print(f"VN30 data with {len(data_top30)} rows has been updated and saved to {to_file}.")

    to_file = "resources/indices/vn100.json"
    data_top100 = data.head(100)
    data_obj = data_top100.to_dict(orient="records")
    final_obj = {
        "date": timestamp,
        "data": data_obj,
    }
    with open(to_file, "w") as f:
        json.dump(final_obj, f, indent=4)
    print(f"VN100 data with {len(data_top100)} rows has been updated and saved to {to_file}.")


async def update_vn_index_hnx():
    url = "https://stockanalysis.com/list/hanoi-stock-exchange/"
    data = await crawler_service.scrape_data_table(url, table_attr_filter={"id": "main-table"})

    # data["Market Cap"] is in the format of "1.5B", "300M", etc. We need to convert it to a number for sorting and filtering.
    data["Market Cap"] = data["Market Cap"].apply(convert_market_cap)

    # sort by market cap in descending order
    data = data.sort_values(by="Market Cap", ascending=False)

    columns_to_drop = ["No.", "Stock Price", "% Change", "Revenue"]
    for column in columns_to_drop:
        if column in data.columns:
            data = data.drop(columns=[column])
    columns_remap = {
        "Symbol": "symbol",
        "Company Name": "company",
        "Market Cap": "market_cap",
    }
    for old_col, new_col in columns_remap.items():
        if old_col in data.columns:
            data = data.rename(columns={old_col: new_col})
    data["symbol"] = data["symbol"].apply(lambda x: "HNX:" + x.strip())
    data["market_cap"] = data["market_cap"].astype(int)

    timestamp = datetime.now().strftime("%Y-%m-%d")

    to_file = "resources/indices/hnx30.json"
    data_top30 = data.head(30)
    data_obj = data_top30.to_dict(orient="records")
    final_obj = {
        "date": timestamp,
        "data": data_obj,
    }
    with open(to_file, "w") as f:
        json.dump(final_obj, f, indent=4)
    print(f"HNX30 data with {len(data_top30)} rows has been updated and saved to {to_file}.")


async def main():
    await update_vn_index_hose()
    await update_vn_index_hnx()


asyncio.run(main())
