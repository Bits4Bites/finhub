import numpy as np
import pandas as pd

# def country_code_from_yf_ticker(yf_ticker: str) -> str:
#     """
#     Gets the country code for a Yahoo Finance ticker.
#
#     Args:
#         yf_ticker (str): The ticker for the Yahoo Finance ticker (e.g. CBA.AX or APPL).
#
#     Returns:
#         str: The country code for the Yahoo Finance ticker, default is US
#     """
#     yf_ticker = yf_ticker.upper()
#     if yf_ticker.endswith(".AX"):
#         return "AU"
#     elif yf_ticker.endswith(".VN"):
#         return "VN"
#     else:
#         return "US"


def calc_rsi(data: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """
    Calculates the Relative Strength Index (RSI) for a given DataFrame of stock prices.

    Args:
        data (DataFrame): The DataFrame of stock prices (obtained from yfinance) with a 'Close' column.
        period (int, optional): The number of periods to use for the RSI calculation. Defaults to 14.

    Returns:
        DataFrame: A DataFrame containing the RSI values, with the same index as the input data.
    """
    delta = data["Close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calc_trend_sma(data: pd.DataFrame, short: int = 50, long: int = 100) -> float:
    """
    Calculates the trend over the period of the data using SMA comparison method.

    Args:
        data (DataFrame): The DataFrame of stock prices (obtained from yfinance) with a 'Close' column.
        short (int, optional): The number of periods to use for the SMA calculation. Defaults to 50.
        long (int, optional): The number of periods to use for the SMA calculation. Defaults to 100.

    Returns:
        float: The trend over the period of the stock prices (MA-short - MA-long) / MA-long
    """
    if len(data) < long or len(data) < short:
        return 0
    sma_short = data["Close"].rolling(window=short).mean()
    sma_long = data["Close"].rolling(window=long).mean()
    result = float((sma_short.iloc[-1] - sma_long.iloc[-1]) / sma_long.iloc[-1])
    return result


def calc_trend_ema(data: pd.DataFrame, short: int = 21, long: int = 55) -> float:
    """
    Calculates the trend over the period of the data using EMA comparison method.

    Args:
        data (DataFrame): The DataFrame of stock prices (obtained from yfinance) with a 'Close' column.
        short (int, optional): The number of periods to use for the SMA calculation. Defaults to 21.
        long (int, optional): The number of periods to use for the SMA calculation. Defaults to 55.

    Returns:
        float: The trend over the period of the stock prices (MA-short - MA-long) / MA-long
    """
    if len(data) < long or len(data) < short:
        return 0
    ema_short = data["Close"].ewm(span=short).mean()
    ema_long = data["Close"].ewm(span=long).mean()
    result = float((ema_short.iloc[-1] - ema_long.iloc[-1]) / ema_long.iloc[-1])
    return result


def find_volume_spikes(data: pd.DataFrame, threshold_multiplier: float = 2.5) -> pd.DataFrame:
    """
    Identifies volume spikes in the stock data.
    A volume spike is defined as a day when the trading volume is greater than the average volume over the period multiplied by the threshold_multiplier.
    """
    avg_volume = data["Volume"].mean()
    threshold = avg_volume * threshold_multiplier
    spikes = data[data["Volume"] >= threshold]
    return spikes


def analyze_past_dividends(data: pd.DataFrame, recovery_days_threshold: int = 28) -> pd.DataFrame:
    """
    Analyzes the past dividends over the period of the stock data.

    Args:
        data (DataFrame): The DataFrame of stock prices (obtained from yfinance) with 'Close' and 'Dividends' column.
        recovery_days_threshold (int, optional): The number of days to look for price recovery after the ex-dividend date. Defaults to 28.

    Returns:
        DataFrame: A DataFrame containing the dividend analysis, with the same index as the input data, containing columns for dividend analysis
    """
    # Algorithm:
    # - Ex-Div date is the date where fields Dividends > 0
    # - For each Ex-Div date:
    #   - Get value of Close field of the previous date (PreExDivPrice)
    #   - For the next recovery_days_threshold days, check for the first date where Close price >= PreExDivPrice, or None if not found
    dividend_data = data[data["Dividends"] > 0].copy()
    if dividend_data.empty:
        return dividend_data
    if recovery_days_threshold < 1:
        recovery_days_threshold = 10

    dividend_data["DVT"] = (
        (dividend_data["Open"] + dividend_data["Close"] + dividend_data["High"] + dividend_data["Low"])
        / 4
        * dividend_data["Volume"]
    )
    dividend_data = dividend_data[["Dividends", "Open", "Close", "Volume", "DVT"]]
    dividend_data["PreExDivPrice"] = data["Close"].shift(1)
    # for t in [1,3,5,10,20,30]:
    #     dividend_data[f"DRE{t}"] = (data["Close"].shift(-t)-dividend_data["PreExDivPrice"]) / (dividend_data["Dividends"]*sqrt(t))

    # dividend_data["Drop"] = dividend_data["PreExDivPrice"] - dividend_data["Open"]  # drop amount
    # # set to 0 if Drop < 0
    # # dividend_data["Drop"] = dividend_data["Drop"].apply(lambda x: x if x > 0 else 0)
    # dividend_data["DropRatio"] = dividend_data["Drop"] / dividend_data["Dividends"]

    dividend_data["RecoveryDays"] = None
    dividend_data["PostExDivPeak"] = None
    dividend_data["PostExDivFloor"] = None
    for idx in dividend_data.index:
        pre_ex_div_price = dividend_data.at[idx, "PreExDivPrice"]
        for i in range(1, recovery_days_threshold + 1):
            if idx + pd.Timedelta(days=i) in data.index:
                close_price = data.at[idx + pd.Timedelta(days=i), "Close"]
                if (
                    dividend_data.at[idx, "PostExDivPeak"] is None
                    or close_price > dividend_data.at[idx, "PostExDivPeak"]
                ):
                    # peak price can continue after recovery
                    dividend_data.at[idx, "PostExDivPeak"] = close_price
                if dividend_data.at[idx, "PostExDivFloor"] is None or (
                    close_price < dividend_data.at[idx, "PostExDivFloor"]
                    and dividend_data.at[idx, "RecoveryDays"] is None
                ):
                    # only set floor price if not recovered yet
                    dividend_data.at[idx, "PostExDivFloor"] = close_price
                if (
                    close_price >= pre_ex_div_price
                    and dividend_data.at[idx, "Volume"] > 0
                    and dividend_data.at[idx, "RecoveryDays"] is None
                ):
                    # recovery day is the first day close_price >= pre_ex_div_price and has transacted volume
                    dividend_data.at[idx, "RecoveryDays"] = i

    # price might drop a few days later, not exactly on the ex-div day
    dividend_data["Drop"] = dividend_data["PreExDivPrice"] - dividend_data["PostExDivFloor"]
    dividend_data["DropRatio"] = dividend_data["Drop"] / dividend_data["Dividends"]

    return dividend_data


def calc_bid_ask_spread_roll(data: pd.DataFrame) -> float | None:
    """
    Calculates the bid/ask spread over the period of the stock data, using Roll’s Estimator

    Args:
        data (DataFrame): The DataFrame of stock prices (obtained from yfinance) with 'Close' column.

    Returns:
        float: The bid/ask spread over the period of the stock data, calculated using Roll’s Estimator
    """
    if len(data) < 2:
        return None
    data = data.copy()
    data["Price_Change"] = data["Close"].diff()
    data["Prev_Price_Change"] = data["Price_Change"].shift(1)

    # Calculate covariance between today's change and yesterday's change
    cov = data["Price_Change"].cov(data["Prev_Price_Change"])

    if cov < 0:
        # Roll's formula
        estimated_spread_dollar = 2 * np.sqrt(-cov)
        latest_close = data["Close"].iloc[-1]
        estimated_spread = estimated_spread_dollar / latest_close
        return float(estimated_spread)

    # Roll's Estimator failed (Covariance is positive). Stock is trending too hard.
    return None
