from __future__ import annotations

import statistics
from datetime import UTC, datetime
from typing import Any

import pandas as pd
import yfinance as yf
from pydantic import BaseModel, Field

from ..utils import asset as asset_utils
from ..utils import conv, yfutils
from . import types


class SymbolBase(BaseModel):
    """Canonical identity and market metadata shared by symbol models."""

    symbol: str = Field(description="Provider-native security symbol.")
    normalized_symbol: str = Field(
        default="",
        description="Canonical EXCHANGE:CODE symbol.",
    )
    currency: str = Field(description="Trading currency code.")
    exchange: str = Field(description="Normalized exchange code.")
    country: str = Field(description="ISO market country code.")

    def __init__(self, ticker: yf.Ticker, /, **data: Any):
        super().__init__(
            symbol=ticker.info.get("symbol"),
            currency=ticker.info.get("currency"),
            exchange=ticker.info.get("fullExchangeName", ticker.info.get("exchange")),
            country=ticker.info.get("country", ticker.info.get("region", "US")),
            **data,
        )
        self.country = conv.country_to_iso2(self.country)
        self.exchange = conv.normalize_exchange_code(self.exchange)
        self.normalized_symbol = conv.to_exch_symb_format(ticker=ticker)


class HistoryPoint(BaseModel):
    """One historical market-price observation and derived indicators."""

    timestamp: int = Field(description="Unix timestamp of the market observation.")
    timestamp_str: str = Field(description="Timezone-aware display timestamp.")
    currency: str = Field(default="", description="Currency of the price values.")
    open: float = Field(default=0.0, description="Opening price.")
    high: float = Field(default=0.0, description="Highest price.")
    low: float = Field(default=0.0, description="Lowest price.")
    close: float = Field(default=0.0, description="Closing price.")
    volume: int = Field(default=0, description="Trading volume.")
    dividends: float | None = Field(
        default=None,
        description="Dividend amount recorded for the observation.",
    )
    rsi14: float | None = Field(
        default=None,
        description="Fourteen-period relative strength index.",
    )
    dvt: float | None = Field(
        default=None,
        description="Approximate daily value traded.",
    )

    def to_currency(self, currency: str, x_rate: float) -> HistoryPoint:
        return self.model_copy(
            update={
                "currency": currency,
                "open": self.open * x_rate,
                "high": self.high * x_rate,
                "low": self.low * x_rate,
                "close": self.close * x_rate,
                "dividends": self.dividends * x_rate if self.dividends else None,
                "rsi14": self.rsi14 * x_rate if self.rsi14 else None,
                "dvt": self.dvt * x_rate if self.dvt else None,
            }
        )


class SymbolOverview(SymbolBase):
    """Company profile, classification, and high-level financial metrics."""

    short_name: str | None = Field(default=None, description="Short issuer or security name.")
    long_name: str | None = Field(default=None, description="Full issuer or security name.")
    sector: str | None = Field(default=None, description="Provider-reported economic sector.")
    industry: str | None = Field(default=None, description="Provider-reported industry.")
    website: str | None = Field(default=None, description="Issuer website URL.")
    description: str | None = Field(
        default=None,
        description="Issuer business summary.",
    )
    quote_type: str | None = Field(
        default=None,
        description="Provider-native quote or instrument type.",
    )
    asset_type: types.AssetType | None = Field(
        default=None,
        description="Normalized FinHub asset classification.",
    )
    total_cash: int | None = Field(default=None, description="Most recently reported total cash.")
    total_cash_per_share: float | None = Field(
        default=None,
        description="Most recently reported cash per share.",
    )
    total_debt: int | None = Field(default=None, description="Most recently reported total debt.")
    total_debt_per_share: float | None = Field(
        default=None,
        description="Most recently reported debt per share.",
    )
    total_revenue: int | None = Field(
        default=None,
        description="Most recently reported total revenue.",
    )
    total_revenue_per_share: float | None = Field(
        default=None,
        description="Most recently reported revenue per share.",
    )
    ebitda: int | None = Field(
        default=None,
        description="Most recently reported earnings before interest, taxes, depreciation, and amortization.",
    )
    ebitda_margins: float | None = Field(
        default=None,
        description="EBITDA margin expressed as a decimal ratio.",
    )
    earnings_growth: float | None = Field(
        default=None,
        description="Provider-reported earnings growth rate.",
    )
    revenue_growth: float | None = Field(
        default=None,
        description="Provider-reported revenue growth rate.",
    )
    gross_margins: float | None = Field(
        default=None,
        description="Gross margin expressed as a decimal ratio.",
    )
    operating_margins: float | None = Field(
        default=None,
        description="Operating margin expressed as a decimal ratio.",
    )
    profit_margins: float | None = Field(
        default=None,
        description="Profit margin expressed as a decimal ratio.",
    )
    market_cap: int | None = Field(
        default=None,
        description="Current market capitalization.",
    )
    cap_size: types.MarketCapType | None = Field(
        default=None,
        description="FinHub market-capitalization size category.",
    )
    market_index: str | None = Field(
        default=None,
        description="Recognized market index containing the security.",
    )

    def __init__(self, ticker: yf.Ticker, /, **data: Any):
        super().__init__(
            ticker,
            short_name=ticker.info.get("shortName"),
            long_name=ticker.info.get("longName"),
            sector=ticker.info.get("sector"),
            industry=ticker.info.get("industry"),
            website=ticker.info.get("website"),
            description=ticker.info.get("longBusinessSummary"),
            quote_type=ticker.info.get("quoteType"),
            total_cash=ticker.info.get("totalCash"),
            total_cash_per_share=ticker.info.get("totalCashPerShare"),
            total_debt=ticker.info.get("totalDebt"),
            total_debt_per_share=ticker.info.get("totalDebtPerShare"),
            total_revenue=ticker.info.get("totalRevenue"),
            total_revenue_per_share=ticker.info.get("totalRevenuePerShare"),
            ebitda=ticker.info.get("ebitda"),
            ebitda_margins=ticker.info.get("ebitdaMargins"),
            earnings_growth=ticker.info.get("earningsGrowth"),
            revenue_growth=ticker.info.get("revenueGrowth"),
            gross_margins=ticker.info.get("grossMargins"),
            operating_margins=ticker.info.get("operatingMargins"),
            profit_margins=ticker.info.get("profitMargins"),
            market_cap=ticker.info.get("marketCap"),
            **data,
        )
        # self.total_cash = int(self.total_cash) if self.total_cash is not None else None
        # self.total_cash_per_share = float(self.total_cash_per_share) if self.total_cash_per_share is not None else None
        # self.total_debt = int(self.total_debt) if self.total_debt is not None else None
        # self.total_debt_per_share = float(self.total_debt_per_share) if self.total_debt_per_share is not None else None
        # self.total_revenue = int(self.total_revenue) if self.total_revenue is not None else None
        # self.total_revenue_per_share = (
        #     float(self.total_revenue_per_share) if self.total_revenue_per_share is not None else None
        # )
        # self.ebitda = int(self.ebitda) if self.ebitda is not None else None
        # self.ebitda_margins = float(self.ebitda_margins) if self.ebitda_margins is not None else None
        # self.earnings_growth = float(self.earnings_growth) if self.earnings_growth is not None else None
        # self.revenue_growth = float(self.revenue_growth) if self.revenue_growth is not None else None
        # self.gross_margins = float(self.gross_margins) if self.gross_margins is not None else None
        # self.operating_margins = float(self.operating_margins) if self.operating_margins is not None else None
        # self.profit_margins = float(self.profit_margins) if self.profit_margins is not None else None
        # self.market_cap = int(self.market_cap) if self.market_cap is not None else None
        self.cap_size, self.market_index = yfutils.classify_market_cap(ticker)

        # detect asset type
        self.asset_type = asset_utils.detect_asset_type(
            quote_type=self.quote_type,
            sector=self.sector,
            industry=self.industry,
            corp_name=self.long_name or self.short_name,
        )


class SymbolDividend(BaseModel):
    """Current and historical dividend attributes for a security."""

    dividend_rate: float = Field(
        default=0.0,
        description="Forward annualized dividend amount per share.",
    )
    dividend_yield: float = Field(
        default=0.0,
        description="Forward annual dividend yield as a percentage.",
    )
    payout_frequency: int = Field(
        default=0,
        description="Number of dividend payments observed during the past year.",
    )
    ex_dividend_date: int = Field(
        default=0,
        description="Unix timestamp of the next or latest ex-dividend date.",
    )
    ex_dividend_date_str: str | None = Field(
        default=None,
        description="Exchange-local display value of the ex-dividend timestamp.",
    )
    five_year_avg_dividend_yield: float = Field(
        default=0.0,
        description="Provider-reported five-year average dividend yield.",
    )
    trailing_annual_dividend_rate: float = Field(
        default=0.0,
        description="Trailing annual dividend amount per share.",
    )
    trailing_annual_dividend_yield: float = Field(
        default=0.0,
        description="Trailing annual dividend yield.",
    )
    last_dividend_value: float = Field(
        default=0.0,
        description="Most recently reported dividend amount per share.",
    )
    last_dividend_date: int = Field(
        default=0,
        description="Unix timestamp of the most recent dividend payment.",
    )
    last_dividend_date_str: str | None = Field(
        default=None,
        description="Exchange-local display value of the latest dividend timestamp.",
    )

    def __init__(self, ticker: yf.Ticker):
        super().__init__(
            dividend_rate=ticker.info.get("dividendRate", 0),
            dividend_yield=ticker.info.get("dividendYield", 0),
            ex_dividend_date=ticker.info.get("exDividendDate", 0),
            five_year_avg_dividend_yield=ticker.info.get("fiveYearAvgDividendYield", 0),
            trailing_annual_dividend_rate=ticker.info.get("trailingAnnualDividendRate", 0),
            trailing_annual_dividend_yield=ticker.info.get("trailingAnnualDividendYield", 0),
            last_dividend_value=ticker.info.get("lastDividendValue", 0),
            last_dividend_date=ticker.info.get("lastDividendDate", 0),
        )
        tz = yfutils.tz_from_yf_ticker(ticker)
        if self.ex_dividend_date:
            self.ex_dividend_date_str = (
                datetime.fromtimestamp(self.ex_dividend_date, tz=UTC)
                .replace(tzinfo=tz)
                .isoformat(sep=" ", timespec="seconds")
            )
        if self.last_dividend_date:
            self.last_dividend_date_str = (
                datetime.fromtimestamp(self.last_dividend_date, tz=UTC)
                .replace(tzinfo=tz)
                .isoformat(sep=" ", timespec="seconds")
            )

        # calculate payout frequency
        history365d = ticker.history(period="365d", interval="1d", auto_adjust=False)
        idx = history365d.index[-1] - pd.Timedelta(days=365)
        self.payout_frequency = int((history365d[idx:]["Dividends"] > 0).sum())


class StockQuote(BaseModel):
    """Current quote, valuation, and analyst-target data for a security."""

    currency: str | None = Field(default="", description="Currency of quote and target prices.")
    market_price: float | None = Field(
        default=0.0,
        description="Latest regular-market price.",
    )
    market_price_change: float | None = Field(
        default=None,
        description="Absolute regular-market price change.",
    )
    market_price_change_percent: float | None = Field(
        default=None,
        description="Regular-market price change as a percentage.",
    )
    market_open: float | None = Field(default=None, description="Regular-market opening price.")
    market_day_high: float | None = Field(
        default=None,
        description="Regular-market session high.",
    )
    market_day_low: float | None = Field(
        default=None,
        description="Regular-market session low.",
    )
    fifty_two_week_high: float | None = Field(
        default=None,
        description="Highest price during the trailing 52 weeks.",
    )
    fifty_two_week_low: float | None = Field(
        default=None,
        description="Lowest price during the trailing 52 weeks.",
    )
    market_volume: int | None = Field(
        default=None,
        description="Latest regular-market trading volume.",
    )
    bid: float | None = Field(default=None, description="Latest bid price.")
    bid_size: int | None = Field(default=None, description="Latest bid size.")
    ask: float | None = Field(default=None, description="Latest ask price.")
    ask_size: int | None = Field(default=None, description="Latest ask size.")
    market_cap: int | None = Field(
        default=None,
        description="Current market capitalization.",
    )
    trailing_eps: float | None = Field(
        default=None,
        description="Trailing twelve-month earnings per share.",
    )
    forward_eps: float | None = Field(
        default=None,
        description="Forward consensus earnings per share.",
    )
    trailing_p_e: float | None = Field(
        default=None,
        description="Trailing price-to-earnings ratio.",
    )
    forward_p_e: float | None = Field(
        default=None,
        description="Forward price-to-earnings ratio.",
    )
    beta: float | None = Field(default=None, description="Provider-reported equity beta.")
    recommendation_key: str | None = Field(
        default=None,
        description="Provider-normalized analyst recommendation.",
    )
    target_high_price: float | None = Field(
        default=None,
        description="Highest reported analyst target price.",
    )
    target_low_price: float | None = Field(
        default=None,
        description="Lowest reported analyst target price.",
    )
    target_mean_price: float | None = Field(
        default=None,
        description="Mean reported analyst target price.",
    )
    target_median_price: float | None = Field(
        default=None,
        description="Median reported analyst target price.",
    )

    def __init__(self, ticker: yf.Ticker):
        super().__init__(
            currency=ticker.info.get("currency"),
            market_price=ticker.info.get("regularMarketPrice"),
            market_price_change=ticker.info.get("regularMarketChange"),
            market_price_change_percent=ticker.info.get("regularMarketChangePercent"),
            market_open=ticker.info.get("regularMarketOpen"),
            market_day_high=ticker.info.get("regularMarketDayHigh"),
            market_day_low=ticker.info.get("regularMarketDayLow"),
            fifty_two_week_high=ticker.info.get("fiftyTwoWeekHigh"),
            fifty_two_week_low=ticker.info.get("fiftyTwoWeekLow"),
            market_volume=ticker.info.get("regularMarketVolume"),
            bid=ticker.info.get("bid"),
            bid_size=ticker.info.get("bidSize"),
            ask=ticker.info.get("ask"),
            ask_size=ticker.info.get("askSize"),
            market_cap=ticker.info.get("marketCap"),
            trailing_eps=(
                ticker.info.get("trailingEps")
                if ticker.info.get("trailingEPS")
                else ticker.info.get("epsTrailingTwelveMonths")
                if ticker.info.get("epsTrailingTwelveMonths")
                else None
            ),
            forward_eps=ticker.info.get("forwardEps"),
            trailing_p_e=ticker.info.get("trailingPE"),
            forward_p_e=ticker.info.get("forwardPE"),
            beta=ticker.info.get("beta") if ticker.info.get("beta") else ticker.info.get("beta3Year"),
            recommendation_key=ticker.info.get("recommendationKey"),
            target_high_price=ticker.info.get("targetHighPrice"),
            target_low_price=ticker.info.get("targetLowPrice"),
            target_mean_price=ticker.info.get("targetMeanPrice"),
            target_median_price=ticker.info.get("targetMedianPrice"),
        )

    def to_currency(self, currency: str, x_rate: float) -> StockQuote:
        return self.model_copy(
            update={
                "currency": currency,
                "market_price": self.market_price * x_rate if self.market_price else None,
                "market_price_change": self.market_price_change * x_rate if self.market_price_change else None,
                "market_open": self.market_open * x_rate if self.market_open else None,
                "market_day_high": self.market_day_high * x_rate if self.market_day_high else None,
                "market_day_low": self.market_day_low * x_rate if self.market_day_low else None,
                "fifty_two_week_high": self.fifty_two_week_high * x_rate if self.fifty_two_week_high else None,
                "fifty_two_week_low": self.fifty_two_week_low * x_rate if self.fifty_two_week_low else None,
                "bid": self.bid * x_rate if self.bid else None,
                "ask": self.ask * x_rate if self.ask else None,
                "trailing_eps": self.trailing_eps * x_rate if self.trailing_eps else None,
                "forward_eps": self.forward_eps * x_rate if self.forward_eps else None,
                "target_high_price": self.target_high_price * x_rate if self.target_high_price else None,
                "target_low_price": self.target_low_price * x_rate if self.target_low_price else None,
                "target_mean_price": self.target_mean_price * x_rate if self.target_mean_price else None,
                "target_median_price": self.target_median_price * x_rate if self.target_median_price else None,
            }
        )


class StockHistory(BaseModel):
    """Recent price history and derived technical indicators."""

    recent_high_price: float = Field(
        default=0.0,
        description="Highest closing price in the recent 30-day lookback.",
    )
    pull_pack_percent: float = Field(
        default=0.0,
        description="Percentage pullback from the recent high.",
    )
    current_volume: int = Field(
        default=0,
        description="Most recent daily trading volume.",
    )
    yesterday_volume: int = Field(
        default=0,
        description="Previous trading day's volume.",
    )
    average_volume_30d: int = Field(
        default=0,
        description="Average daily volume over the recent 30-day lookback.",
    )
    ma10: float = Field(default=0.0, description="Ten-day simple moving average.")
    ma20: float = Field(default=0.0, description="Twenty-day simple moving average.")
    ma50: float = Field(default=0.0, description="Fifty-day simple moving average.")
    ma100: float = Field(default=0.0, description="One-hundred-day simple moving average.")
    ma200: float = Field(default=0.0, description="Two-hundred-day simple moving average.")
    rsi14: float = Field(default=0.0, description="Fourteen-period relative strength index.")
    history_90d: list[HistoryPoint] = Field(
        default=[],
        description="Up to 90 recent daily price observations.",
    )

    def __init__(self, ticker: yf.Ticker):
        super().__init__()
        currency = ticker.info.get("currency", "")
        history365d = ticker.history(period="365d", interval="1d", auto_adjust=False)
        history30d = history365d.iloc[-30:]

        # calculate pullback if any
        self.recent_high_price = history30d["Close"].iloc[:-2].max()
        current_price = history365d["Close"].iloc[-1]
        self.pull_pack_percent = (
            (self.recent_high_price - current_price) * 100 / self.recent_high_price if self.recent_high_price else 0
        )

        # calculate moving averages
        self.current_volume = int(history365d["Volume"].iloc[-1])
        self.yesterday_volume = int(history365d["Volume"].iloc[-2])
        self.average_volume_30d = int(history30d["Volume"].iloc[:-2].mean())
        self.ma10 = history365d["Close"].rolling(window=10).mean().iloc[-1] or 0.0
        self.ma20 = history365d["Close"].rolling(window=20).mean().iloc[-1] or 0.0
        self.ma50 = history365d["Close"].rolling(window=50).mean().iloc[-1] or 0.0
        self.ma100 = history365d["Close"].rolling(window=100).mean().iloc[-1] or 0.0
        self.ma200 = history365d["Close"].rolling(window=200).mean().iloc[-1] or 0.0

        # calculate Relative Strength Index (RSI)
        delta = history365d["Close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        self.rsi14 = rsi.iloc[-1]

        # store history for 90 days
        if len(history365d) >= 30:
            num_points = 90 if len(history365d) >= 90 else 60 if len(history365d) >= 60 else 30
            self.history_90d = [
                HistoryPoint(
                    timestamp=int(history365d.index[-num_points + i].timestamp()),
                    # history365d.index[-NUM_POINTS + i] is already in correct timezone
                    timestamp_str=history365d.index[-num_points + i].isoformat(sep=" ", timespec="seconds"),
                    currency=currency,
                    open=history365d.iloc[-num_points + i]["Open"],
                    high=history365d.iloc[-num_points + i]["High"],
                    low=history365d.iloc[-num_points + i]["Low"],
                    close=history365d.iloc[-num_points + i]["Close"],
                    volume=int(history365d.iloc[-num_points + i]["Volume"]),
                    dividends=history365d.iloc[-num_points + i]["Dividends"],
                    rsi14=rsi.iloc[-num_points + i],
                    dvt=statistics.fmean(
                        [
                            history365d.iloc[-num_points + i]["High"],
                            history365d.iloc[-num_points + i]["Low"],
                            history365d.iloc[-num_points + i]["Open"],
                            history365d.iloc[-num_points + i]["Close"],
                        ]
                    )
                    * history365d.iloc[-num_points + i]["Volume"],
                )
                for i in range(0, num_points)
            ]


class SymbolInfo(SymbolOverview):
    """Comprehensive symbol profile with quote, dividend, and history data."""

    stock_quote: StockQuote = Field(description="Current quote and valuation data.")
    dividend: SymbolDividend = Field(description="Current and historical dividend attributes.")
    stock_history: StockHistory = Field(description="Recent history and technical indicators.")

    def __init__(self, ticker: yf.Ticker):
        super().__init__(
            ticker,
            stock_quote=StockQuote(ticker),
            dividend=SymbolDividend(ticker),
            stock_history=StockHistory(ticker),
        )


# ----------------------------------------------------------------------#
# Resolve forward reference: DividendEventAnalysis.overview -> SymbolOverview
from . import event as _event_models  # noqa: E402

_event_models.DividendEventAnalysis.model_rebuild()
