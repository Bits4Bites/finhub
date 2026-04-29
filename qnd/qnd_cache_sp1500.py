# Run with the following command from the parent company:
# $ python -m qnd.qnd_cache_sp1500

import asyncio
import json
import logging
import yfinance as yf

from app.services import stock as stock_service
from app.models import finhub as models


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
    data = []
    files = [
        "./resources/indices/sp500.json",
        "./resources/indices/spmidcap400.json",
        "./resources/indices/spsmallcap600.json",
    ]
    for file in files:
        json_content = read_file_as_single_string(file)
        if json_content:
            file_data = json.loads(json_content)
            data += file_data["data"]

    cache_data = {}
    num_total = len(data)
    num_cached = 0

    for row in data:
        symbol = row["symbol"].strip()
        ticker = yf.Ticker(f"{symbol.split(":")[-1]}")
        quote_type = ticker.info["quoteType"] if "quoteType" in ticker.info else "NONE"
        if quote_type == "NONE":
            print(f"Symbol: {symbol} / No quoteType found")
            continue
        if quote_type not in stock_service.allowed_quote_types:
            print(f"Symbol: {symbol} / Invalid quoteType found: {quote_type}")
            continue
        if "regularMarketPrice" not in ticker.info:
            print(f"Symbol: {symbol} / No regularMarketPrice found")
            continue

        num_cached += 1
        try:
            symbol_data = models.SymbolOverview(ticker)
            cache_data[symbol] = symbol_data.model_dump()
        except Exception as e:
            print(f"Symbol: {symbol} / Invalid symbol found: {e}")
            print(ticker.info)
            raise

        if num_cached % 10 == 0:
            print(f"Total symbols: {num_total} / Cached symbols: {num_cached}")

    print(f"Total symbols: {num_total} / Cached symbols: {num_cached}")
    with open("./.cache_data/sp1500_cache.json", "w", encoding="utf-8") as cache_file:
        json.dump(cache_data, cache_file, ensure_ascii=False, indent=4)


asyncio.run(main())
