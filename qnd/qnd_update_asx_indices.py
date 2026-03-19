# Run with the following command from the parent company:
# $ python -m qnd.qnd_asx_index

import asyncio

from app.services import crawler as crawler_service

async def update_asx_index(index: str, num_check: int):
    url = "https://www.dividenddates.com.au/asx-300-list/"
    to_file = "resources/indices/asx300.json"
    index = index.upper()
    match index:
        case "ASX50" | "ASX-50":
            url = "https://www.dividenddates.com.au/asx-50-list/"
            to_file = "resources/indices/asx50.json"
        case "ASX100" | "ASX-100":
            url = "https://www.dividenddates.com.au/asx-100-list/"
            to_file = "resources/indices/asx100.json"
        case "ASX200" | "ASX-200":
            url = "https://www.dividenddates.com.au/asx-200-list/"
            to_file = "resources/indices/asx200.json"

    data = await crawler_service.scrape_data_table(url)
    if data is None or data.empty:
        raise EnvironmentError(f"No data available from {url}.")
    data = data.drop(columns=["Weight (%)"]).rename(
        columns={
            "Code": "symbol",
            "Company": "company",
            "Sector": "sector",
            "Market Cap": "market_cap",
        },
    )
    if len(data) < num_check:
        raise ValueError(f"Expected at least {num_check} entries, but got {len(data)}.")
    data.to_json(to_file, orient="records")
    print(f"{index} data with {len(data)} rows has been updated and saved to {to_file}.")


async def main():
    await update_asx_index("ASX50", 45)
    await update_asx_index("ASX100", 85)
    await update_asx_index("ASX200", 160)
    await update_asx_index("ASX300", 250)


asyncio.run(main())
