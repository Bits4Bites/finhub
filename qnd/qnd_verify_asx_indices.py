# Run with the following command from the parent company:
# $ python -m qnd.qnd_verify_asx_indices

import asyncio
import json
import logging

from app.utils import finhub as finhub_utils

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")


def read_file_as_single_string(file_path) -> str:
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            lines = [line.rstrip() for line in file]
            combined_text = "\n".join(lines)
        return combined_text
    except FileNotFoundError:
        logging.error("Error: File '%s' not found.", file_path)
    except PermissionError:
        logging.error("Error: Permission denied for file '%s'.", file_path)
    except Exception as e:
        logging.exception("An unexpected error occurred while reading file '%s': '%e'", file_path, e)
    return ""


async def main():
    cache_json_content = read_file_as_single_string("./.cache/asx_cache.json")
    cache_ticker_info = json.loads(cache_json_content)

    data = []
    files = [
        "./resources/indices/asx300.json",
    ]
    for file in files:
        json_content = read_file_as_single_string(file)
        if json_content:
            file_data = json.loads(json_content)
            data += file_data["data"]
    num_total = len(data)
    num_found_sector = 0
    num_found_industry = 0
    sectors = {}
    industries = {}
    for row in data:
        symbol = row["symbol"].strip()
        ticker_info = cache_ticker_info[symbol] if symbol in cache_ticker_info else None
        if ticker_info is None:
            continue

        sector = ticker_info["sector"] if "sector" in ticker_info else None
        sector = sector.upper() if sector is not None else "NONE"
        # if sector != "REAL ESTATE":
        #     continue

        found_sector = sector in finhub_utils.asx_sector_yf_indices
        num_found_sector += found_sector
        if found_sector:
            sectors[sector] = True

        # industry = ticker_info["industry"] if "industry" in ticker_info else None
        # industry = industry.upper() if industry is not None else "NONE"
        # found_industry = industry in finhub_utils.us_industry_yf_indices[sector]
        # num_found_industry += found_industry
        # if found_industry:
        #     industries[industry] = True
        # print(f"Symbol: {symbol} / Sector: {sector} {"✅" if found_sector else "❌"} / Industry: {industry} {"✅" if found_industry else "❌"}")
        print(f"Symbol: {symbol} / Sector: {sector} {"✅" if found_sector else "❌"}")

    print(f"Number of found/total: {num_found_sector}-{num_found_industry} / {num_total}")
    print(f"Unique sectors found: {sectors.keys()}")
    print(f"Unique industries found: {industries.keys()}")


asyncio.run(main())
