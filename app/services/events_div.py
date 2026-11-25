import datetime
import math
import typing
import zoneinfo

import starlette.concurrency
import yfinance as yf

from ..models import events_div as models_event
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
    country = conv.country_to_iso2(country)
    end_date = datetime.datetime.now(tz).date() + (
        datetime.timedelta(days=20) if country == "AU" else datetime.timedelta(days=10)
    )
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

    raw_data = raw_data[raw_data["Exchange"].notna() & (raw_data["Exchange"].astype(str).str.upper() != "N/A")].copy()
    if raw_data.empty:
        return []

    raw_data = raw_data.rename(
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
    )
    if country == "VN":
        raw_data["cat"] = "dividend"
    else:
        raw_data["cat"] = (
            raw_data["corp"]
            .fillna(raw_data["sym"])
            .astype(str)
            .apply(
                lambda name: (
                    "distribution"
                    if any(kw in name.upper() for kw in ["TRUST", "FUND", "REIT", "ETF", "PROPERTY"])
                    else "dividend"
                )
            )
        )

    raw_data_json = raw_data.to_json(orient="records") or ""
    events = models_event.parse_upcoming_dividend_events_from_json(raw_data_json, default_vals)
    for event in events:
        event.symbol = f"{event.exchange}:{event.symbol}"
        event.timestamp_str = conv.yyyymmdd_to_iso(event.timestamp_str or "", tz=tz) or event.timestamp_str
        event.timestamp = int(datetime.datetime.fromisoformat(event.timestamp_str or "").timestamp())
        if event.payment_date:
            event.payment_date = conv.yyyymmdd_to_iso(event.payment_date, tz=tz)
    return events


async def get_asx_upcoming_dividends_events(index: str = "") -> list[models_event.UpcomingDividendEvent]:
    """Return normalized upcoming ASX dividend and distribution events.

    Args:
        index: Optional ASX index filter. Supported values are ``ASX20``,
            ``ASX50``, ``ASX100``, ``ASX200``, and ``ASX300``; matching is
            case-insensitive.

    Returns:
        Declared events with exchange-qualified symbols, Sydney timestamps,
        AUD amounts, ASX links, and ``dividend`` or ``distribution`` categories.
        Returns an empty list for an unsupported index, no source rows, or no
        matching constituents.

    Raises:
        ValueError: If required announcement fields are missing or values are
            malformed, including invalid event dates.
        KeyError: If a requested supported index is not loaded.

    Notes:
        Issuer names containing ``FUND``, ``TRUST``, ``REIT``, ``ETF``, or
        ``PROPERTY`` are classified as ``distribution`` (case-insensitive);
        all other issuers are classified as ``dividend``. Source order is
        preserved after filtering. Missing amounts and yields use ``0.0``.
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
    """Return normalized upcoming US dividend and distribution events.

    Args:
        index: Optional index filter. Supported values are ``NASDAQ100``,
            ``SP500``, ``SP400``, and ``SP600``; matching is case-insensitive.

    Returns:
        Declared events with exchange-qualified symbols, New York timestamps,
        USD amounts, StockAnalysis links, and ``dividend`` or ``distribution``
        categories. Rows whose exchange cannot be identified are omitted.
        Returns an empty list for an unsupported index, no usable source rows,
        or no matching constituents.

    Raises:
        ValueError: If required announcement fields are missing or values are
            malformed, including invalid event dates.
        KeyError: If a requested supported index is not loaded.

    Notes:
        Issuer names containing ``FUND``, ``TRUST``, ``REIT``, ``ETF``, or
        ``PROPERTY`` are classified as ``distribution`` (case-insensitive);
        all other issuers are classified as ``dividend``. Source order is
        preserved after filtering. Missing amounts and yields use ``0.0``.
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
    """Return normalized upcoming Vietnamese cash-dividend events.

    Args:
        index: Optional index filter. Supported values are ``VN30``, ``VN100``,
            and ``HNX30``; matching is case-insensitive.

    Returns:
        Declared cash-dividend events with exchange-qualified symbols, Ho Chi
        Minh City timestamps, VND amounts, VietStock links, and category
        ``dividend``. Returns an empty list for an unsupported index, no usable
        source rows, or no matching constituents.

    Raises:
        ValueError: If required announcement fields are missing or values are
            malformed, including invalid event dates.
        KeyError: If a requested supported index is not loaded.

    Notes:
        The underlying VietStock crawler supports cash dividends only; stock
        dividends and bonus-share events are outside this service contract.
        Every returned event is classified as ``dividend``, and source order
        is preserved after filtering. Missing amounts and rates use ``0.0``.
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
    ticker: yf.Ticker | None = None,
    symbol: str,
    ex_date: str,
    div_amount: float,
) -> models_event.DividendEventMetrics | None:
    """Estimate price-drop and recovery behavior for a dividend event.

    Args:
        ticker: Optional preloaded Yahoo Finance ticker for the subject
            security.
        symbol: Subject security in Yahoo format or ``EXCHANGE:CODE`` format.
        ex_date: Upcoming ex-dividend date in ``YYYY-MM-DD`` format.
        div_amount: Announced dividend amount per share.

    Returns:
        Historical drop, recovery, liquidity, momentum, and benchmark metrics.
        Returns ``None`` for unsupported quote types, a missing or non-positive
        current price, fewer than 90 completed history rows, or no analyzable
        historical dividend events.

    Raises:
        ValueError: If ``ex_date`` is not a valid ``YYYY-MM-DD`` date.
        KeyError: If provider history is missing required price, volume, or
            dividend columns.

    Notes:
        Quote types ``EQUITY``, ``ETF``, and ``MUTUALFUND`` are supported.
        Historical recovery is evaluated over 28 calendar days. A supplied
        ticker is still expected to provide Yahoo-compatible ``info`` and
        ``history`` data. ``div_yield`` is the announced event amount divided
        by the current price. ``drop_price_min`` and ``drop_price_max`` are
        non-negative drop amounts calculated by applying the historical mean
        drop-to-dividend ratio, plus or minus one standard deviation, to the
        announced amount; they are not post-drop price levels. Provider and
        timezone failures are not suppressed.
    """
    return await starlette.concurrency.run_in_threadpool(
        _analyse_dividend_event_sync,
        ticker=ticker,
        symbol=symbol,
        ex_date=ex_date,
        div_amount=div_amount,
    )


def _analyse_dividend_event_sync(
    *,
    ticker: yf.Ticker | None = None,
    symbol: str,
    ex_date: str,
    div_amount: float,
) -> models_event.DividendEventMetrics | None:
    """Fetch synchronous market data and calculate dividend-event metrics."""
    yf_ticker = conv.to_yf_symbol_format(symbol)
    ticker = yf.Ticker(yf_ticker) if ticker is None else ticker
    tz = yfutils.tz_from_yf_ticker(ticker)

    info = ticker.info or {}
    quote_type = info.get("quoteType")
    if quote_type not in allowed_quote_types:
        return None

    current_price = float(info.get("regularMarketPrice") or 0)
    if current_price <= 0:
        return None
    timestamp_str = conv.yyyymmdd_to_iso(ex_date, tz=tz)
    if timestamp_str is None:
        raise ValueError("ex_date must use YYYY-MM-DD format")

    result = models_event.DividendEventMetrics(
        symbol=info.get("symbol", ""),
        exchange=conv.normalize_exchange_code(info.get("fullExchangeName") or info.get("exchange") or ""),
        company_name=info.get("longName") or info.get("shortName") or "(n/a)",
        timestamp_str=timestamp_str,
        price=current_price,
        div_amount=div_amount,
        div_yield=div_amount / current_price,
    )
    result.timestamp = int(datetime.datetime.fromisoformat(result.timestamp_str or "").timestamp())

    history = ticker.history(period="5y", interval="1d", auto_adjust=False)
    # intentionally remove the last row, which may be incomplete for the current day
    history5y = history.iloc[:-1].copy()
    if len(history5y) < 90:
        return None
    history5y = history5y.tz_convert(tz)

    recovery_days_threshold = 28
    past_dividends_analysis = finhub_utils.analyze_past_dividends(history5y, recovery_days_threshold)
    if past_dividends_analysis.empty:
        return None
    result.num_samples = len(past_dividends_analysis)

    avg_drop_ratio = past_dividends_analysis["DropRatio"].mean()
    std_drop_ratio = past_dividends_analysis["DropRatio"].std()
    if math.isnan(std_drop_ratio):
        std_drop_ratio = 0.0
    min_drop = div_amount * (avg_drop_ratio - std_drop_ratio)
    max_drop = div_amount * (avg_drop_ratio + std_drop_ratio)
    result.drop_price_min = max(0.0, float(min(min_drop, max_drop)))
    result.drop_price_max = max(0.0, float(max(min_drop, max_drop)))

    recovery_days = past_dividends_analysis["RecoveryDays"]
    median_recovery_days = recovery_days.median()
    std_recovery_days = recovery_days.std() if recovery_days.count() > 1 else 0.0
    if math.isnan(median_recovery_days) or math.isnan(std_recovery_days):
        result.recovery_days_min = recovery_days_threshold + 1
        result.recovery_days_max = result.recovery_days_min + 1
    else:
        result.recovery_days_min = max(1, int(median_recovery_days - std_recovery_days))
        result.recovery_days_max = int(median_recovery_days + std_recovery_days)

    total_rows = len(past_dividends_analysis)
    num_recovery_max = (past_dividends_analysis["RecoveryDays"].notna()).sum()
    result.recovery_probability = float(num_recovery_max / total_rows)

    recovery_data = past_dividends_analysis[past_dividends_analysis["RecoveryDays"].notna()]
    if not recovery_data.empty:
        mean_overshoot = (recovery_data["PostExDivPeak"] - recovery_data["PreExDivPrice"]).mean()
        result.recovery_price_min = current_price
        result.recovery_price_max = float(current_price + mean_overshoot)

    result.beta = info.get("beta", 0) or 0
    history7d = history5y[-7:].copy()
    history7d["DVT"] = (
        (history7d["Open"] + history7d["Close"] + history7d["High"] + history7d["Low"]) / 4 * history7d["Volume"]
    )
    result.avg_dvt_7d = int(history7d["DVT"].mean())
    result.std_dvt_7d = int(history7d["DVT"].std())
    history30d = history5y[-30:]
    result.rsi14 = int(finhub_utils.calc_rsi(history30d, 14).iloc[-1])
    result.avg_volume_30d = int(history30d["Volume"].mean())
    result.std_volume_30d = int(history30d["Volume"].std())
    result.bid_ask_spread = finhub_utils.calc_bid_ask_spread_roll(history5y[-30:]) or 0.0

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
