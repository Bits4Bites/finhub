import yfinance as yf

from ..models import market_data as models_market_data


def get_gold_quote(currency: str = "USD") -> models_market_data.StockQuote | None:
    """Fetch the current gold-futures quote in a requested currency.

    Args:
        currency: Target currency code. Matching is case-insensitive; an empty
            value uses USD.

    Returns:
        The USD quote or its converted value, or ``None`` when Yahoo does not
        support the requested conversion currency.

    Notes:
        Provider, conversion, and model-validation failures propagate.
    """
    x_rate = 1.0
    currency = currency.strip().upper() or "USD"
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
    """Fetch ordered daily gold-futures history in a requested currency.

    Args:
        currency: Target currency code. Matching is case-insensitive; an empty
            value uses USD.
        num_days: Requested history length. Non-positive values use 30 days.

    Returns:
        History points in provider order, an empty list when no observations are
        available, or ``None`` when Yahoo does not support the requested
        conversion currency.

    Notes:
        Provider, conversion, and model-validation failures propagate.
    """
    x_rate = 1.0
    currency = currency.strip().upper() or "USD"
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
    """Fetch the current silver-futures quote in a requested currency.

    Args:
        currency: Target currency code. Matching is case-insensitive; an empty
            value uses USD.

    Returns:
        The USD quote or its converted value, or ``None`` when Yahoo does not
        support the requested conversion currency.

    Notes:
        Provider, conversion, and model-validation failures propagate.
    """
    x_rate = 1.0
    currency = currency.strip().upper() or "USD"
    if currency != "" and currency != "USD":
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
    """Fetch ordered daily silver-futures history in a requested currency.

    Args:
        currency: Target currency code. Matching is case-insensitive; an empty
            value uses USD.
        num_days: Requested history length. Non-positive values use 30 days.

    Returns:
        History points in provider order, an empty list when no observations are
        available, or ``None`` when Yahoo does not support the requested
        conversion currency.

    Notes:
        Provider, conversion, and model-validation failures propagate.
    """
    x_rate = 1.0
    currency = currency.strip().upper() or "USD"
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
