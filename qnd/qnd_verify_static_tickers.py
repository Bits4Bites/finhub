# Run with the following command from the parent company:
# $ python -m qnd.qnd_verify_static_tickers

import asyncio
import logging

import yfinance as yf

from app.utils import finhub as finhub_utils

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

def verify1layer(name: str, data: dict[str, str]):
    logging.info(f"Checking '{name}'...")
    for k, symbol in data.items():
        ticker = yf.Ticker(symbol)
        if "symbol" in ticker.info:
            history = ticker.history(period="5y", interval="1d")
            n = len(history)
            if n < 365:
                logging.error(f"Ticker {k}: {symbol} has less than 1 year of history: {n}")
        else:
            logging.warning(f"No ticker {k}: {symbol}")


def verify2layers(name: str, data: dict[str, dict[str, str]]):
    logging.info(f"Checking '{name}'...")
    skip = False
    for s, sg in data.items():
        for k, symbol in sg.items():
            ticker = yf.Ticker(symbol)
            if "symbol" in ticker.info:
                history = ticker.history(period="5y", interval="1d")
                n = len(history)
                if n < 365:
                    logging.error(f"Ticker {s}/{k}: {symbol} has less than 1 year of history: {n}")
                    ticker = yf.Ticker(symbol[:-2])
                    history = ticker.history(period="5y", interval="1d")
                    n = len(history)
                    if n < 365:
                        logging.error(f"Ticker {s}/{k}: {symbol[:-2]} has less than 1 year of history: {n}")
                        ticker = yf.Ticker(symbol[:-4])
                        history = ticker.history(period="5y", interval="1d")
                        n = len(history)
                        if n < 365:
                            logging.error(f"Ticker {s}/{k}: {symbol[:-4]} has less than 1 year of history: {n}")
                        else:
                            logging.info(f"Ticker {s}/{k}: found {symbol[:-4]}")
                    else:
                        logging.info(f"Ticker {s}/{k}: found {symbol[:-2]}")
                    skip = True
            else:
                logging.warning(f"No ticker {s}/{k}: {symbol}")
        if skip:
            return


async def main():
    verify1layer("asx_index_yf_static_tickers", finhub_utils.asx_index_yf_static_tickers)
    verify1layer("asx_sector_yf_static_tickers", finhub_utils.asx_sector_yf_static_tickers)

    verify1layer('us_index_yf_static_tickers', finhub_utils.us_index_yf_static_tickers)

    verify1layer('us_sector_yf_static_tickers', finhub_utils.us_sector_yf_static_tickers)
    verify2layers("us_industry_yf_static_tickers", finhub_utils.us_industry_yf_static_tickers)

    # verify1layer('us_sector_yf_static_tickers_sp400', finhub_utils.us_sector_yf_static_tickers_sp400)

    # verify1layer('us_sector_yf_static_tickers_sp600', finhub_utils.us_sector_yf_static_tickers_sp600)


asyncio.run(main())
