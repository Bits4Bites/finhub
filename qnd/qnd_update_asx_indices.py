# Run with the following command from the parent company:
# $ python -m qnd.qnd_update_asx_indices

import asyncio
import json
from datetime import datetime

from app.services import crawler as crawler_service

async def update_asx_index(index: str, num_check: int):
    url = "https://www.dividenddates.com.au/asx-300-list/"
    to_file = "resources/indices/asx300.json"
    table_attr_filter = None
    index = index.upper()
    match index:
        case "ASX20" | "ASX 20" | "ASX-20":
            url = "https://fnarena.com/index/ASX20/"
            to_file = "resources/indices/asx20.json"
            table_attr_filter = {"id": "table_index"}
        case "ASX50" | "ASX 50" | "ASX-50":
            url = "https://www.dividenddates.com.au/asx-50-list/"
            to_file = "resources/indices/asx50.json"
        case "ASX100" | "ASX 100" | "ASX-100":
            url = "https://www.dividenddates.com.au/asx-100-list/"
            to_file = "resources/indices/asx100.json"
        case "ASX200" | "ASX 200" | "ASX-200":
            url = "https://www.dividenddates.com.au/asx-200-list/"
            to_file = "resources/indices/asx200.json"

    data = await crawler_service.scrape_data_table(url, table_attr_filter=table_attr_filter)
    if data is None or data.empty:
        raise EnvironmentError(f"No data available from {url}.")
    if len(data) < num_check:
        raise ValueError(f"Expected at least {num_check} entries, but got {len(data)}.")

    colums_to_drop = ["Weight (%)", "#", "PRICE", "RECS", "Market Cap", "CONSENSUSTARGET"]
    for col in colums_to_drop:
        if col in data.columns:
            data = data.drop(columns=[col])

    columns_remap = {
        "Code": "symbol",
        "Company": "company",
        "Sector": "sector",
        "SYMBOL": "symbol",
        "COMPANY NAME": "company",
        "SECTOR (FNARENA)": "sector",
    }
    for old_col, new_col in columns_remap.items():
        if old_col in data.columns:
            data = data.rename(columns={old_col: new_col})

    # add prefix "ASX:" to each row of column "symbol"
    data["symbol"] = data["symbol"].apply(lambda x: f"ASX:{x.upper().strip()}")
    timestamp = datetime.now().strftime("%Y-%m-%d")
    data_obj = data.to_dict(orient="records")
    # data.to_json(to_file, orient="records")
    final_obj = {
        "date": timestamp,
        "data": data_obj,
    }
    json.dump(final_obj, open(to_file, "w"), indent=4)
    print(f"{index} data with {len(data)} rows has been updated and saved to {to_file}.")


async def main():
    await update_asx_index("ASX20", 18)
    await update_asx_index("ASX50", 45)
    await update_asx_index("ASX100", 85)
    await update_asx_index("ASX200", 160)
    await update_asx_index("ASX300", 250)


asyncio.run(main())
