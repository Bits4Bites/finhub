import math
import typing
import zoneinfo
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

from ..models import event as models_event
from ..services import crawler_div as services_crawler_div
from ..utils import asset as asset_utils
from ..utils import conv, yfutils
from ..utils import finhub as finhub_utils

allowed_quote_types = {"EQUITY", "ETF", "MUTUALFUND"}


async def _get_upcoming_dividends_events(
    country: str,
    tz: zoneinfo.ZoneInfo,
    *,
    default_vals: dict[str, typing.Any] | None = None,
) -> list[models_event.UpcomingDividendEvent]:
    """
    Check for upcoming dividend/distribution events (AU, US & VN only).

    Args:
        country (str): Country code to filter events by (e.g., 'AU', 'US', etc.).
        tz (ZoneInfo): Timezone to use for date calculations.
        default_vals (str, optional): internal use

    Returns:
        list[models_event.UpcomingDividendEvent]: A list of upcoming dividend/distribution events
    """
    country = conv.country_to_iso2(country)
    end_date = datetime.now(tz).date() + (timedelta(days=60) if country == "AU" else timedelta(days=30))
    raw_data = (
        await services_crawler_div.scrape_dividends_asx(end_date)
        if country == "AU"
        else (
            await services_crawler_div.scrape_dividends_vn(end_date)
            if country == "VN"
            else await services_crawler_div.scrape_dividends_us(end_date)
        )
    )
    if raw_data.empty:
        return []

    # remove rows where "Exchange" column is "N/A"
    raw_data = raw_data[raw_data["Exchange"] != "N/A"]

    # final transformation of raw_data
    # - rename column "Ticker" to "sym"
    # - rename column "Exchange" to "exchange"
    # - rename column "Company" to "corp"
    # - rename column "Ex-Div Date" to "date"
    # - rename column "Payment Date" to "pdate"
    # - rename column "Div Amount" to "amount"
    # - rename column "Div Yield" to "yield"
    # - rename column "Currency" to "currency"
    raw_data.rename(
        columns={
            "Ticker": "sym",
            "Exchange": "exchange",
            "Company": "corp",
            "Ex-Div Date": "date",
            "Payment Date": "pdate",
            "Div Amount": "amount",
            "Div Yield": "yield",
            "Currency": "currency",
        },
        inplace=True,
    )
    # - add column event_category: "distribution" if company_name contains Trust, Fund, REIT, ETF, or Property. Else "dividend"
    raw_data["cat"] = raw_data["corp"].apply(
        lambda name: (
            "distribution"
            if any(kw in name.upper() for kw in ["TRUST", "FUND", "REIT", "ETF", "PROPERTY"])
            else "dividend"
        )
    )

    raw_data_json = raw_data.to_json(orient="records") or ""
    events = models_event.parse_upcoming_dividend_events_from_json(raw_data_json, default_vals)
    for event in events:
        event.symbol = f"{event.exchange}:{event.symbol}"
        event.timestamp_str = conv.yyyymmdd_to_iso(event.timestamp_str or "", tz=tz) or event.timestamp_str
        event.timestamp = int(datetime.fromisoformat(event.timestamp_str or "").timestamp())
        if event.payment_date:
            event.payment_date = conv.yyyymmdd_to_iso(event.payment_date, tz=tz)
    return events


async def get_asx_upcoming_dividends_events(index: str = "") -> list[models_event.UpcomingDividendEvent]:
    """
    Check for upcoming dividend/distribution events for ASX.

    Args:
        index (str, optional): ASX index to filter stocks (e.g. ASX20, ASX50, ASX100, ASX200 and ASX300)

    Returns:
        list[models_event.UpcomingDividendEvent]: A list of upcoming dividend/distribution events
    """
    asx_indices = ["ASX20", "ASX50", "ASX100", "ASX200", "ASX300"]
    normalized_index = index.upper() if index else ""
    if normalized_index and normalized_index not in asx_indices:
        return []

    country = "AU"
    tz = zoneinfo.ZoneInfo("Australia/Sydney")
    default_vals = {
        "src": "ASX",
        "status": "declared",
    }
    events = await _get_upcoming_dividends_events(country, tz, default_vals=default_vals)
    if normalized_index:
        events = [e for e in events if asset_utils.is_in_index(index=normalized_index, symbol=e.symbol)]

    for event in events:
        event.link = f"https://www.asx.com.au/markets/company/{event.symbol.split(':')[-1]}"
    return events


async def get_us_upcoming_dividends_events(index: str = "") -> list[models_event.UpcomingDividendEvent]:
    """
    Check for upcoming dividend/distribution events for US market.

    Args:
        index (str, optional): index to filter stocks (e.g. NASDAQ100, SP500, SP400 and SP600)

    Returns:
        list[models_event.UpcomingDividendEvent]: A list of upcoming dividend/distribution events
    """
    us_indices = ["NASDAQ100", "SP500", "SP400", "SP600"]
    normalized_index = index.upper() if index else ""
    if normalized_index and normalized_index not in us_indices:
        return []

    country = "US"
    tz = zoneinfo.ZoneInfo("America/New_York")
    default_vals = {
        "src": "StockAnalysis",
        "status": "declared",
    }
    events = await _get_upcoming_dividends_events(country, tz, default_vals=default_vals)
    if normalized_index:
        events = [e for e in events if asset_utils.is_in_index(index=normalized_index, symbol=e.symbol)]

    for event in events:
        event.link = f"https://stockanalysis.com/stocks/{event.symbol.lower().split(':')[-1]}/dividend/"
    return events


async def get_vn_upcoming_dividends_events(index: str = "") -> list[models_event.UpcomingDividendEvent]:
    """
    Check for upcoming dividend/distribution events for US market.

    Args:
        index (str, optional): index to filter stocks (e.g. VN30, VN100 and HNX30)

    Returns:
        list[models_event.UpcomingDividendEvent]: A list of upcoming dividend/distribution events
    """
    vn_indices = ["VN30", "VN100", "HNX30"]
    normalized_index = index.upper() if index else ""
    if normalized_index and normalized_index not in vn_indices:
        return []

    country = "VN"
    tz = zoneinfo.ZoneInfo("Asia/Ho_Chi_Minh")
    default_vals = {
        "src": "VietStock",
        "status": "declared",
    }
    events = await _get_upcoming_dividends_events(country, tz, default_vals=default_vals)
    if normalized_index:
        events = [e for e in events if asset_utils.is_in_index(index=normalized_index, symbol=e.symbol)]

    for event in events:
        event.link = f"https://finance.vietstock.vn/{event.symbol.split(':')[-1]}-thong-tin.htm"
    return events


# ----------------------------------------------------------------------#


async def analyse_dividend_event(
    *,
    ticker: yf.Ticker = None,
    symbol: str,
    ex_date: str,
    div_amount: float,
) -> models_event.DividendEventAnalysis | None:
    """
    Analyzes a dividend event to estimate price range and recovery probability.

    Args:
        ticker (yf.Ticker, optional): Pre-created yfinance Ticker object for the stock for reuse/caching purpose. If not provided, it will be created within the function.
        symbol (str): Stock ticker symbol, accept YF format (`CBA.AX`) or `EXCHANGE:CODE` format (`NASDAQ:AAPL`)
        ex_date (str): Ex-dividend date in ISO format (YYYY-MM-DD).
        div_amount (float): Dividend amount per share.

    Returns:
        models_event.DividendEventAnalysis: An object containing the analysis of the dividend event
    """
    yf_ticker = conv.to_yf_symbol_format(symbol)
    ticker = yf.Ticker(yf_ticker) if ticker is None else ticker
    tz = yfutils.tz_from_yf_ticker(ticker)

    quote_type = ticker.info.get("quoteType")
    if quote_type not in allowed_quote_types:
        return None
    # if quote_type == "NONE":
    #     return None  # no data available
    # if quote_type not in allowed_quote_types:
    #     raise ValueError(f"Quote type '{quote_type}' for ticker '{ticker}' is not supported for dividend analysis.")

    info = ticker.info
    current_price = info.get("regularMarketPrice", 0)
    result = models_event.DividendEventAnalysis(
        # overview=models.SymbolOverview(ticker),
        symbol=info.get("symbol", ""),
        exchange=conv.normalize_exchange_code(info.get("fullExchangeName") or info.get("exchange") or ""),
        company_name=info.get("longName") or info.get("shortName") or "(n/a)",
        # timestamp: int = 0
        timestamp_str=conv.yyyymmdd_to_iso(ex_date, tz=tz),
        # event_category: str | None = None
        # source_name: str | None = None
        # link: str | None = None
        price=current_price,
        div_amount=div_amount,
        div_yield=(div_amount / current_price) if current_price else 0.0,
        # ex_div_date=conv.yyyymmdd_to_iso(ex_date, tz=tz),
    )
    # result.ex_div_date_timestamp = int(datetime.fromisoformat(result.ex_div_date or "").timestamp())
    result.timestamp = int(datetime.datetime.fromisoformat(result.timestamp_str or "").timestamp())

    history = ticker.history(period="5y", interval="1d", auto_adjust=False)
    history5y = history[:-1]
    if len(history5y) < 90:
        return None  # not enough data
    history5y = history5y.tz_convert(tz)

    # recalculate div-yield
    idx = history5y.index[-1] - pd.Timedelta(days=365)
    sum_div = float(history5y[idx:]["Dividends"].sum())
    result.div_yield = sum_div / current_price

    recovery_days_threshold = 28
    past_dividends_analysis = finhub_utils.analyze_past_dividends(history5y, recovery_days_threshold)
    if past_dividends_analysis.empty:
        return None  # not enough historical data
    result.num_samples = len(past_dividends_analysis)

    # estimate price drop
    avg_drop_ratio = past_dividends_analysis["DropRatio"].mean()
    std_drop_ratio = past_dividends_analysis["DropRatio"].std()
    min_drop = div_amount * (avg_drop_ratio - std_drop_ratio)
    max_drop = div_amount * (avg_drop_ratio + std_drop_ratio)
    # technically cant be lower than 0.0, right?
    result.drop_price_min = max(0.0, float(current_price - max_drop))
    result.drop_price_max = max(0.0, float(current_price - min_drop))

    # estimate recovery days
    median_recovery_days = past_dividends_analysis["RecoveryDays"].median()
    std_recovery_days = past_dividends_analysis["RecoveryDays"].std()
    if math.isnan(median_recovery_days) or math.isnan(std_recovery_days):
        result.recovery_days_min = recovery_days_threshold + 1
        result.recovery_days_max = result.recovery_days_min or 0 + 1
    else:
        result.recovery_days_min = max(1, int(median_recovery_days - std_recovery_days))
        result.recovery_days_max = int(median_recovery_days + std_recovery_days)

    # estimate recovery chance
    total_rows = len(past_dividends_analysis)
    num_recovery_max = (past_dividends_analysis["RecoveryDays"].notna()).sum()
    result.recovery_probability = float(num_recovery_max / total_rows)

    # estimate recovery price
    recovery_data = past_dividends_analysis[past_dividends_analysis["RecoveryDays"].notna()]
    if not recovery_data.empty:
        mean_overshoot = (recovery_data["PostExDivPeak"] - recovery_data["PreExDivPrice"]).mean()
        result.recovery_price_min = current_price
        result.recovery_price_max = float(current_price + mean_overshoot)

    # additional technical data
    result.beta = ticker.info.get("beta", 0)
    history7d = history5y[-7:]
    history7d["DVT"] = (
        (history7d["Open"] + history7d["Close"] + history7d["High"] + history7d["Low"]) / 4 * history7d["Volume"]
    )
    result.avg_dvt_7d = int(history7d["DVT"].mean())
    result.std_dvt_7d = int(history7d["DVT"].std())
    history30d = history5y[-30:]
    result.rsi14 = int(finhub_utils.calc_rsi(history30d, 14).iloc[-1])
    result.avg_volume_30d = int(history30d["Volume"].mean())
    result.std_volume_30d = int(history30d["Volume"].std())
    result.bid_ask_spread = finhub_utils.calc_bid_ask_spread_roll(history[-30:]) or 0.0

    result.trend_60d = finhub_utils.calc_trend_ema(history5y[-60:])
    market_ticker = yfutils.lookup_index_yf_static_symbol(ticker=ticker)
    if market_ticker is not None:
        mt = yf.Ticker(market_ticker)
        if "symbol" in mt.info:
            market_history60d = mt.history(period="61d", interval="1d", auto_adjust=False)[:-1]
            market_history60d = market_history60d.tz_convert(tz)
            result.market_trend_60d = finhub_utils.calc_trend_ema(market_history60d)
    peer_ticker = yfutils.lookup_peer_yf_static_symbol(ticker=ticker)
    if peer_ticker is not None:
        pt = yf.Ticker(peer_ticker)
        if "symbol" in pt.info:
            peer_history60d = pt.history(period="61d", interval="1d", auto_adjust=False)[:-1]
            peer_history60d = peer_history60d.tz_convert(tz)
            result.peer_trend_60d = finhub_utils.calc_trend_ema(peer_history60d)

    return result
