# Run with the following command from the parent company:
# $ python -m qnd.qnd_verify_static_tickers

import asyncio
import logging

import yfinance as yf

from app.utils import finhub as finhub_utils

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

async def main():
    logging.info("Checking 'asx_index_yf_static_tickers'")
    for k, symbol in finhub_utils.asx_index_yf_static_tickers.values():
        ticker = yf.Ticker(symbol)
        if "symbol" in ticker.info:
            logging.info(f"Found ticker {k}: {symbol}")
        else:
            logging.warning(f"No ticker {k}: {symbol}")

    logging.info("Checking 'asx_sector_yf_static_tickers'")
    for k, symbol in finhub_utils.asx_sector_yf_static_tickers.values():
        ticker = yf.Ticker(symbol)
        if "symbol" in ticker.info:
            logging.info(f"Found ticker {k}: {symbol}")
        else:
            logging.warning(f"No ticker {k}: {symbol}")


asyncio.run(main())
