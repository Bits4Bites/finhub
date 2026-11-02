import yfinance as yf

from ..models import market_data as models_market_data


def get_gold_quote(currency: str = "USD") -> models_market_data.StockQuote | None:
    """
    Get the current gold price in the specified currency.

    Args:
        currency (str): The currency code (e.g., "USD", "EUR") to get the price in.

    Returns:
        models_market_data.StockQuote | None: The current price, or None when unavailable.
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
    quote = models_market_data.StockQuote(ticker)

    if currency != "" and currency != "USD":
        # finally, convert the price to the specified currency
        quote = quote.to_currency(currency, x_rate)

    return quote


def get_gold_history(currency: str = "USD", num_days: int = 30) -> list[models_market_data.HistoryPoint] | None:
    """
    Get the historical gold prices for the specified period and currency.

    Args:
        currency (str): The currency code (e.g., "USD", "EUR") to get the prices in.
        num_days (int): The number of days of historical data to retrieve (default is 30).

    Returns:
        list[models_market_data.HistoryPoint] | None: Historical prices, or None when unavailable.
    """
    x_rate = 1.0
    currency = currency.upper()
    if currency != "" and currency != "USD":
        # first, check if the currency is supported by yfinance
        ticker = yf.Ticker(f"USD{currency}=X")
        if "currency" not in ticker.info:
            return None
        x_rate = float(ticker.info["regularMarketPrice"])

    num_days = 30 if num_days <= 0 else num_days

    # second, get the historical prices in USD
    ticker = yf.Ticker("GC=F")  # Gold Futures
    hist = ticker.history(period=f"{num_days}d", interval="1d", auto_adjust=False)

    points = [
        models_market_data.HistoryPoint(
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


def get_silver_quote(currency: str = "USD") -> models_market_data.StockQuote | None:
    """
    Get the current silver price in the specified currency.

    Args:
        currency (str): The currency code (e.g., "USD", "EUR") to get the price in.

    Returns:
        models_market_data.StockQuote | None: The current price, or None when unavailable.
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
    quote = models_market_data.StockQuote(ticker)

    if currency != "" and currency != "USD":
        # finally, convert the price to the specified currency
        quote = quote.to_currency(currency, x_rate)

    return quote


def get_silver_history(currency: str = "USD", num_days: int = 30) -> list[models_market_data.HistoryPoint] | None:
    """
    Get the historical silver prices for the specified period and currency.

    Args:
        currency (str): The currency code (e.g., "USD", "EUR") to get the prices in.
        num_days (int): The number of days of historical data to retrieve (default is 30).

    Returns:
        list[models_market_data.HistoryPoint] | None: Historical prices, or None when unavailable.
    """
    x_rate = 1.0
    currency = currency.upper()
    if currency != "" and currency != "USD":
        # first, check if the currency is supported by yfinance
        ticker = yf.Ticker(f"USD{currency}=X")
        if "currency" not in ticker.info:
            return None
        x_rate = float(ticker.info["regularMarketPrice"])

    num_days = 30 if num_days <= 0 else num_days

    # second, get the historical prices in USD
    ticker = yf.Ticker("SI=F")  # SILVER Futures
    hist = ticker.history(period=f"{num_days}d", interval="1d", auto_adjust=False)

    points = [
        models_market_data.HistoryPoint(
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
