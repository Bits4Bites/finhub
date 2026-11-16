import numpy as np
import pandas as pd


def calc_rsi(data: pd.DataFrame, period: int = 14) -> pd.Series:
    """Measure price momentum with the simple-average Relative Strength Index.

    Args:
        data: Historical prices containing a ``Close`` column.
        period: The positive number of observations used for momentum.

    Returns:
        RSI values aligned with the input index. The first ``period - 1`` values
        are unavailable. Later values range from 0 to 100, with 50 representing
        unchanged prices.

    Raises:
        KeyError: If ``data`` does not contain ``Close``.
        ValueError: If ``period`` is not positive.

    Notes:
        This function uses simple rolling averages of gains and losses rather
        than Wilder smoothing.
    """
    if period < 1:
        raise ValueError("period must be positive")

    delta = data["Close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.mask((gain == 0) & (loss == 0), 50.0)


def calc_trend_sma(data: pd.DataFrame, short: int = 50, long: int = 100) -> float:
    """Measure relative price trend by comparing short and long simple averages.

    Args:
        data: Historical prices containing a ``Close`` column.
        short: The positive observation window for the short average.
        long: The positive observation window for the long average.

    Returns:
        The relative difference ``(short average - long average) / long average``.
        Returns ``0.0`` when there are not enough observations.

    Raises:
        KeyError: If ``data`` does not contain ``Close``.
        ValueError: If either observation window is not positive.
    """
    if short < 1 or long < 1:
        raise ValueError("short and long periods must be positive")
    close = data["Close"]
    if len(data) < long or len(data) < short:
        return 0.0
    sma_short = close.rolling(window=short).mean()
    sma_long = close.rolling(window=long).mean()
    result = float((sma_short.iloc[-1] - sma_long.iloc[-1]) / sma_long.iloc[-1])
    return result


def calc_trend_ema(data: pd.DataFrame, short: int = 21, long: int = 55) -> float:
    """Measure relative price trend using short and long exponential averages.

    Args:
        data: Historical prices containing a ``Close`` column.
        short: The positive observation span for the short exponential average.
        long: The positive observation span for the long exponential average.

    Returns:
        The relative difference ``(short average - long average) / long average``.
        Returns ``0.0`` when there are not enough observations.

    Raises:
        KeyError: If ``data`` does not contain ``Close``.
        ValueError: If either observation span is not positive.

    Notes:
        The averages use full-history adjusted weighting.
    """
    if short < 1 or long < 1:
        raise ValueError("short and long periods must be positive")
    close = data["Close"]
    if len(data) < long or len(data) < short:
        return 0.0
    ema_short = close.ewm(span=short, adjust=True).mean()
    ema_long = close.ewm(span=long, adjust=True).mean()
    result = float((ema_short.iloc[-1] - ema_long.iloc[-1]) / ema_long.iloc[-1])
    return result


def find_volume_spikes(data: pd.DataFrame, threshold_multiplier: float = 2.5) -> pd.DataFrame:
    """Select trading periods whose volume materially exceeds the sample average.

    Args:
        data: Historical market data containing a ``Volume`` column.
        threshold_multiplier: Multiplier applied to the average volume.

    Returns:
        The input rows whose volume is at least the average multiplied by
        ``threshold_multiplier``, preserving their columns and index.

    Raises:
        KeyError: If ``data`` does not contain ``Volume``.
    """
    avg_volume = data["Volume"].mean()
    threshold = avg_volume * threshold_multiplier
    spikes = data[data["Volume"] >= threshold]
    return spikes


def analyze_past_dividends(data: pd.DataFrame, recovery_days_threshold: int = 28) -> pd.DataFrame:
    """Summarize price-drop and recovery behavior around past dividends.

    Args:
        data: Date-indexed market history containing ``Open``, ``High``, ``Low``,
            ``Close``, ``Volume``, and ``Dividends`` columns.
        recovery_days_threshold: Positive number of calendar days after each
            ex-dividend date to inspect.

    Returns:
        One row per ex-dividend event, indexed by ex-dividend date, with columns
        ``Dividends``, ``Open``, ``Close``, ``Volume``, ``DVT``,
        ``PreExDivPrice``, ``RecoveryDays``, ``PostExDivPeak``,
        ``PostExDivFloor``, ``Drop``, and ``DropRatio``. ``DVT`` is the average
        of the ex-date open, high, low, and close multiplied by volume. Peak and
        floor are based on available closing prices in the recovery horizon; the
        floor stops updating after recovery. ``Drop`` is the pre-event close
        minus that floor, and ``DropRatio`` divides the drop by the dividend.

    Raises:
        KeyError: If required market-history columns are missing.
        ValueError: If ``recovery_days_threshold`` is not positive.

    Notes:
        ``RecoveryDays`` counts calendar days until an available close reaches
        the previous close. It is null when no previous close exists or recovery
        does not occur within the requested horizon. The day exactly equal to
        ``recovery_days_threshold`` is included, and each dividend event is
        summarized independently.
    """
    if recovery_days_threshold < 1:
        raise ValueError("recovery_days_threshold must be positive")

    required_columns = {"Open", "High", "Low", "Close", "Volume", "Dividends"}
    missing_columns = required_columns.difference(data.columns)
    if missing_columns:
        raise KeyError(f"missing required columns: {sorted(missing_columns)}")

    # Algorithm:
    # - Ex-Div date is the date where fields Dividends > 0
    # - For each Ex-Div date:
    #   - Get value of Close field of the previous date (PreExDivPrice)
    #   - For the next recovery_days_threshold days, check for the first date where Close price >= PreExDivPrice, or None if not found
    dividend_data = data[data["Dividends"] > 0].copy()
    if dividend_data.empty:
        return pd.DataFrame(
            columns=[
                "Dividends",
                "Open",
                "Close",
                "Volume",
                "DVT",
                "PreExDivPrice",
                "RecoveryDays",
                "PostExDivPeak",
                "PostExDivFloor",
                "Drop",
                "DropRatio",
            ],
            index=dividend_data.index,
        )

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
                if close_price >= pre_ex_div_price and dividend_data.at[idx, "RecoveryDays"] is None:
                    # recovery day is the first day close_price >= pre_ex_div_price
                    dividend_data.at[idx, "RecoveryDays"] = i

    # price might drop a few days later, not exactly on the ex-div day
    dividend_data["Drop"] = dividend_data["PreExDivPrice"] - dividend_data["PostExDivFloor"]
    dividend_data["DropRatio"] = dividend_data["Drop"] / dividend_data["Dividends"]

    return dividend_data


def calc_bid_ask_spread_roll(data: pd.DataFrame) -> float | None:
    """Estimate the relative bid-ask spread from historical closing prices.

    Args:
        data: Historical prices containing a ``Close`` column.

    Returns:
        The Roll spread estimate divided by the latest closing price. Returns
        ``None`` when there is insufficient data or the price changes do not
        support a Roll estimate.

    Raises:
        KeyError: If ``data`` does not contain ``Close``.

    Notes:
        For positive prices, a successful estimate is a positive proportion and
        is unchanged when every closing price is scaled by the same positive
        factor.
    """
    close = data["Close"]
    if len(data) < 2:
        return None
    data = data.copy()
    data["Price_Change"] = close.diff()
    data["Prev_Price_Change"] = data["Price_Change"].shift(1)

    # Calculate covariance between today's change and yesterday's change
    cov = data["Price_Change"].cov(data["Prev_Price_Change"])

    if cov < 0:
        # Roll's formula
        estimated_spread_dollar = 2 * np.sqrt(-cov)
        latest_close = close.iloc[-1]
        estimated_spread = estimated_spread_dollar / latest_close
        return float(estimated_spread)

    # Roll's Estimator failed (Covariance is positive). Stock is trending too hard.
    return None
