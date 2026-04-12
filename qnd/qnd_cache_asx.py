# Run with the following command from the parent company:
# $ python -m qnd.qnd_cache_asx

import asyncio
import json

import pandas as pd
import yfinance as yf

from app.services import stock as stock_service
from app.models import finhub as models


def load_csv_with_pandas(file_path):
    try:
        df = pd.read_csv(file_path)
        return df
    except FileNotFoundError:
        raise FileNotFoundError(f"File not found: {file_path}")
    except pd.errors.EmptyDataError:
        raise ValueError("The CSV file is empty.")
    except pd.errors.ParserError as e:
        raise ValueError(f"Error parsing CSV: {e}")


async def main():
    pd_data = load_csv_with_pandas("./.cache/ASX_Listed_Companies.csv")

    cache_data = {}
    num_total = len(pd_data)
    num_cached = 0

    for _, row in pd_data.iterrows():
        symbol = f"ASX:{row["ASX code"].strip()}"
        ticker = yf.Ticker(f"{symbol.split(":")[-1]}.AX")
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
    with open("./.cache/asx_cache.json", "w", encoding="utf-8") as cache_file:
        json.dump(cache_data, cache_file, ensure_ascii=False, indent=4)


asyncio.run(main())
