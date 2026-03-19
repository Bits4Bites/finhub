# Run with the following command from the parent company:
# $ python -m qnd.qnd_verify_asx_indices

import asyncio
import yfinance as yf

from app.services import crawler as crawler_service, stock as stock_service

from app.utils import finhub as finhub_utils

async def main():
    data = await crawler_service.scrape_data_table("https://fnarena.com/index/ASX300/", {"id": "table_index"})
    num_total = len(data)
    num_found = 0
    for index, row in data.iterrows():
        symbol = row["SYMBOL"].strip()
        ticker = yf.Ticker(f"{symbol}.AX")
        quote_type = ticker.info["quoteType"] if "quoteType" in ticker.info else "NONE"
        if quote_type == "NONE":
            print(f"Symbol: {symbol} / No quoteType found")
            continue
        if quote_type not in stock_service.allowed_quote_types:
            print(f"Symbol: {symbol} / Invalid quoteType found: {quote_type}")
            continue
        sector = ticker.info["sector"].strip().upper() if "sector" in ticker.info else "NONE"
        industry = ticker.info["industry"].strip().upper() if "industry" in ticker.info else "NONE"
        found = sector in finhub_utils.asx_sector_industry_yf_indices or industry in finhub_utils.asx_sector_industry_yf_indices
        if found:
            num_found += 1
        print(f"Symbol: {symbol} ({quote_type}) / Sector: {sector} / Industry: {industry} / Found: {"✅" if found else "❌"}")

    print(f"Number of found/total: {num_found} / {num_total}")

asyncio.run(main())
