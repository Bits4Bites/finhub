from __future__ import annotations

import statistics
from datetime import UTC, datetime
from typing import Any

import pandas as pd
import yfinance as yf
from pydantic import BaseModel

from ..utils import asset as asset_utils
from ..utils import conv, yfutils
from . import ai as models_ai
from . import types


class SymbolBase(BaseModel):
    symbol: str
    normalized_symbol: str = ""
    currency: str
    exchange: str
    country: str

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
    timestamp: int
    timestamp_str: str
    currency: str = ""
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: int = 0
    dividends: float | None = None
    rsi14: float | None = None
    dvt: float | None = None  # Daily Value Traded (Approximated)

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
    short_name: str | None = None
    long_name: str | None = None
    sector: str | None = None
    industry: str | None = None
    website: str | None = None
    description: str | None = None
    quote_type: str | None = None
    asset_type: types.AssetType | None = None
    total_cash: int | None = None
    total_cash_per_share: float | None = None
    total_debt: int | None = None
    total_debt_per_share: float | None = None
    total_revenue: int | None = None
    total_revenue_per_share: float | None = None
    ebitda: int | None = None
    ebitda_margins: float | None = None
    earnings_growth: float | None = None
    revenue_growth: float | None = None
    gross_margins: float | None = None
    operating_margins: float | None = None
    profit_margins: float | None = None
    market_cap: int | None = None
    cap_size: types.MarketCapType | None = None
    market_index: str | None = None

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
    dividend_rate: float = 0.0  # annual dividend amount
    dividend_yield: float = 0.0  # Annual dividend Yield in percentage, value = 3.45 means 3.45%
    payout_frequency: int = 0  # number of payouts per year, value = 12 means monthly
    ex_dividend_date: int = 0
    ex_dividend_date_str: str | None = None
    five_year_avg_dividend_yield: float = 0.0
    trailing_annual_dividend_rate: float = 0.0
    trailing_annual_dividend_yield: float = 0.0
    last_dividend_value: float = 0.0
    last_dividend_date: int = 0
    last_dividend_date_str: str | None = None

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
    currency: str = ""
    market_price: float = 0.0
    market_price_change: float | None = None
    market_price_change_percent: float | None = None
    market_open: float | None = None
    market_day_high: float | None = None
    market_day_low: float | None = None
    fifty_two_week_high: float | None = None
    fifty_two_week_low: float | None = None
    market_volume: int | None = None
    bid: float | None = None
    bid_size: int | None = None
    ask: float | None = None
    ask_size: int | None = None
    market_cap: int | None = None
    trailing_eps: float | None = None
    forward_eps: float | None = None
    trailing_p_e: float | None = None
    forward_p_e: float | None = None
    beta: float | None = None
    recommendation_key: str | None = None
    target_high_price: float | None = None
    target_low_price: float | None = None
    target_mean_price: float | None = None
    target_median_price: float | None = None

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
    recent_high_price: float = 0.0
    pull_pack_percent: float = 0.0  # 12.34 means 12.34%
    current_volume: int = 0
    yesterday_volume: int = 0
    average_volume_30d: int = 0
    ma10: float = 0.0
    ma20: float = 0.0
    ma50: float = 0.0
    ma100: float = 0.0
    ma200: float = 0.0
    rsi14: float = 0.0
    history_90d: list[HistoryPoint] = []

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
    stock_quote: StockQuote
    dividend: SymbolDividend
    stock_history: StockHistory

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


class HoldingTicker(BaseModel):
    ticker: str = ""
    num_shares: float = 0.0
    avg_price: float = 0.0
    market_price: float = 0.0
    target_allocation: float = 0.0
    tags: str | None = None


class PortfolioAnalysis(models_ai.BaseAIResult):
    analysis: str = ""
