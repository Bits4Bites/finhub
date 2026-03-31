import yfinance as yf
from app.models.finhub import StockQuote, HistoryPoint


def get_gold_quote(currency: str = "USD") -> StockQuote | None:
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


def get_gold_history(currency: str = "USD", num_days: int = 30) -> list[HistoryPoint] | None:
    """
    Get the historical gold prices for the specified period and currency.

    Args:
        currency (str): The currency code (e.g., "USD", "EUR") to get the prices in.
        num_days (int): The number of days of historical data to retrieve (default is 30).

    Returns:
        list[HistoryPoint] | None: A list of HistoryPoint objects representing the historical prices, or None if the prices could not be retrieved or the currency is not supported.
    """
    x_rate = 1.0
    currency = currency.upper()
    if currency != "" and currency != "USD":
        # first, check if the currency is supported by yfinance
        ticker = yf.Ticker(f"USD{currency}=X")
        if "currency" not in ticker.info:
            return None
        x_rate = float(ticker.info["regularMarketPrice"])

    num_days = 30 if num_days <= 0 or num_days > 366 else num_days

    # second, get the historical prices in USD
    ticker = yf.Ticker("GC=F")  # Gold Futures
    hist = ticker.history(period=f"{num_days}d", interval="1d", auto_adjust=False)

    points = [
        HistoryPoint(
            timestamp=int(hist.index[i].timestamp()),
            timestamp_str=hist.index[i].isoformat(sep=" ", timespec="seconds"),
            currency=currency,
            open=hist.iloc[i]["Open"],
            high=hist.iloc[i]["High"],
            low=hist.iloc[i]["Low"],
            close=hist.iloc[i]["Close"],
            volume=int(hist.iloc[i]["Volume"]),
        )
        for i in range(0, len(hist))
    ]
    if currency != "" and currency != "USD":
        for i in range(0, len(points)):
            points[i] = points[i].to_currency(currency, x_rate)

    return points


# ----------------------------------------------------------------------#


def get_silver_quote(currency: str = "USD") -> StockQuote | None:
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


def get_silver_history(currency: str = "USD", num_days: int = 30) -> list[HistoryPoint] | None:
    """
    Get the historical silver prices for the specified period and currency.

    Args:
        currency (str): The currency code (e.g., "USD", "EUR") to get the prices in.
        num_days (int): The number of days of historical data to retrieve (default is 30).

    Returns:
        list[HistoryPoint] | None: A list of HistoryPoint objects representing the historical prices, or None if the prices could not be retrieved or the currency is not supported.
    """
    x_rate = 1.0
    currency = currency.upper()
    if currency != "" and currency != "USD":
        # first, check if the currency is supported by yfinance
        ticker = yf.Ticker(f"USD{currency}=X")
        if "currency" not in ticker.info:
            return None
        x_rate = float(ticker.info["regularMarketPrice"])

    num_days = 30 if num_days <= 0 or num_days > 366 else num_days

    # second, get the historical prices in USD
    ticker = yf.Ticker("SI=F")  # SILVER Futures
    hist = ticker.history(period=f"{num_days}d", interval="1d", auto_adjust=False)

    points = [
        HistoryPoint(
            timestamp=int(hist.index[i].timestamp()),
            timestamp_str=hist.index[i].isoformat(sep=" ", timespec="seconds"),
            currency=currency,
            open=hist.iloc[i]["Open"],
            high=hist.iloc[i]["High"],
            low=hist.iloc[i]["Low"],
            close=hist.iloc[i]["Close"],
            volume=int(hist.iloc[i]["Volume"]),
        )
        for i in range(0, len(hist))
    ]
    if currency != "" and currency != "USD":
        for i in range(0, len(points)):
            points[i] = points[i].to_currency(currency, x_rate)

    return points
