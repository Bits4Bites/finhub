import yfinance as yf
from app.models.finhub import StockQuote


def get_gold_quote(currency: str) -> StockQuote | None:
    """
    Get the current gold price in the specified currency.

    Args:
        currency (str): The currency code (e.g., "USD", "EUR") to get the price in.
    Returns:
        StockQuote | None: The current price as a StockQuote object, or None if the price could not be retrieved or the currency is not supported.
    """
    x_rate = 1.0
    currency = currency.upper()
    if currency != "" and currency != "USD":
        # first, check if the currency is supported by yfinance
        ticker = yf.Ticker(f"USD{currency}=X")
        if "currency" not in ticker.info:
            return None
        x_rate = float(ticker.info["regularMarketPrice"])

    # second, get the price in USD
    ticker = yf.Ticker("GC=F")  # Gold Futures
    quote = StockQuote(ticker)

    if currency != "" and currency != "USD":
        # finally, convert the price to the specified currency
        quote = quote.to_currency(currency, x_rate)

    return quote


# ----------------------------------------------------------------------#


def get_silver_quote(currency: str) -> StockQuote | None:
    """
    Get the current silver price in the specified currency.

    Args:
        currency (str): The currency code (e.g., "USD", "EUR") to get the price in.
    Returns:
        StockQuote | None: The current price as a StockQuote object, or None if the price could not be retrieved or the currency is not supported.
    """
    x_rate = 1.0
    currency = currency.upper()
    if currency != "USD":
        # first, check if the currency is supported by yfinance
        ticker = yf.Ticker(f"USD{currency}=X")
        if "currency" not in ticker.info:
            return None
        x_rate = float(ticker.info["regularMarketPrice"])

    # second, get the price in USD
    ticker = yf.Ticker("SI=F")  # Silver Futures
    quote = StockQuote(ticker)

    if currency != "" and currency != "USD":
        # finally, convert the price to the specified currency
        quote = quote.to_currency(currency, x_rate)

    return quote
