from __future__ import annotations

import json
import statistics
from datetime import datetime, timezone

from pydantic import BaseModel
from typing import Optional, Any
import yfinance as yf

from .types import MarketCapType
from ..utils import finhub as finhub_utils


class SymbolBase(BaseModel):
    symbol: str
    currency: str
    exchange: str
    country: str

    def __init__(self, ticker: yf.Ticker, /, **data: Any):
        super().__init__(
            symbol=ticker.info.get("symbol"),
            currency=ticker.info.get("currency"),
            exchange=(
                ticker.info.get("fullExchangeName")
                if ticker.info.get("fullExchangeName")
                else ticker.info.get("exchange")
            ),
            country=ticker.info.get("country", ticker.info.get("region", "US")),
            **data,
        )
        self.country = finhub_utils.country_to_iso2(self.country)
        self.exchange = finhub_utils.normalize_exchange_code(self.exchange)


class HistoryPoint(BaseModel):
    timestamp: int
    timestamp_str: str
    currency: Optional[str] = None
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[int] = None
    dividends: Optional[float] = None
    rsi14: Optional[float] = None
    dvt: Optional[float] = None  # Daily Value Traded (Approximated)

    def to_currency(self, currency: str, x_rate: float) -> "HistoryPoint":
        return self.model_copy(
            update={
                "currency": currency,
                "open": self.open * x_rate if self.open else None,
                "high": self.high * x_rate if self.high else None,
                "low": self.low * x_rate if self.low else None,
                "close": self.close * x_rate if self.close else None,
                "dividends": self.dividends * x_rate if self.dividends else None,
                "rsi14": self.rsi14 * x_rate if self.rsi14 else None,
                "dvt": self.dvt * x_rate if self.dvt else None,
            }
        )


class SymbolOverview(SymbolBase):
    short_name: Optional[str] = None
    long_name: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    website: Optional[str] = None
    description: Optional[str] = None
    quote_type: Optional[str] = None
    total_cash: Optional[int] = None
    total_cash_per_share: Optional[float] = None
    total_debt: Optional[int] = None
    total_debt_per_share: Optional[float] = None
    total_revenue: Optional[int] = None
    total_revenue_per_share: Optional[float] = None
    ebitda: Optional[int] = None
    ebitda_margins: Optional[float] = None
    earnings_growth: Optional[float] = None
    revenue_growth: Optional[float] = None
    gross_margins: Optional[float] = None
    operating_margins: Optional[float] = None
    profit_margins: Optional[float] = None
    market_cap: Optional[int] = None
    cap_size: Optional[MarketCapType] = None
    market_index: Optional[str] = None

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
        self.total_cash = int(self.total_cash) if self.total_cash is not None else None
        self.total_cash_per_share = float(self.total_cash_per_share) if self.total_cash_per_share is not None else None
        self.total_debt = int(self.total_debt) if self.total_debt is not None else None
        self.total_debt_per_share = float(self.total_debt_per_share) if self.total_debt_per_share is not None else None
        self.total_revenue = int(self.total_revenue) if self.total_revenue is not None else None
        self.total_revenue_per_share = (
            float(self.total_revenue_per_share) if self.total_revenue_per_share is not None else None
        )
        self.ebitda = int(self.ebitda) if self.ebitda is not None else None
        self.ebitda_margins = float(self.ebitda_margins) if self.ebitda_margins is not None else None
        self.earnings_growth = float(self.earnings_growth) if self.earnings_growth is not None else None
        self.revenue_growth = float(self.revenue_growth) if self.revenue_growth is not None else None
        self.gross_margins = float(self.gross_margins) if self.gross_margins is not None else None
        self.operating_margins = float(self.operating_margins) if self.operating_margins is not None else None
        self.profit_margins = float(self.profit_margins) if self.profit_margins is not None else None
        self.market_cap = int(self.market_cap) if self.market_cap is not None else None
        self.cap_size, self.market_index = finhub_utils.classify_market_cap(ticker)


class SymbolDividend(BaseModel):
    dividend_rate: Optional[float] = None
    dividend_yield: Optional[float] = None
    ex_dividend_date: Optional[int] = None
    ex_dividend_date_str: Optional[str] = None
    five_year_avg_dividend_yield: Optional[float] = None
    trailing_annual_dividend_rate: Optional[float] = None
    trailing_annual_dividend_yield: Optional[float] = None
    last_dividend_value: Optional[float] = None
    last_dividend_date: Optional[int] = None
    last_dividend_date_str: Optional[str] = None

    def __init__(self, ticker: yf.Ticker):
        super().__init__(
            dividend_rate=ticker.info.get("dividendRate"),
            dividend_yield=ticker.info.get("dividendYield"),
            ex_dividend_date=ticker.info.get("exDividendDate"),
            five_year_avg_dividend_yield=ticker.info.get("fiveYearAvgDividendYield"),
            trailing_annual_dividend_rate=ticker.info.get("trailingAnnualDividendRate"),
            trailing_annual_dividend_yield=ticker.info.get("trailingAnnualDividendYield"),
            last_dividend_value=ticker.info.get("lastDividendValue"),
            last_dividend_date=ticker.info.get("lastDividendDate"),
        )
        symbol = ticker.info.get("symbol")
        tz = finhub_utils.tz_from_yf_ticker(symbol)
        if self.ex_dividend_date:
            self.ex_dividend_date_str = (
                datetime.fromtimestamp(self.ex_dividend_date, tz=timezone.utc)
                .replace(tzinfo=tz)
                .isoformat(sep=" ", timespec="seconds")
            )
        if self.last_dividend_date:
            self.last_dividend_date_str = (
                datetime.fromtimestamp(self.last_dividend_date, tz=timezone.utc)
                .replace(tzinfo=tz)
                .isoformat(sep=" ", timespec="seconds")
            )


class StockQuote(BaseModel):
    currency: Optional[str] = None
    market_price: Optional[float] = None
    market_price_change: Optional[float] = None
    market_price_change_percent: Optional[float] = None
    market_open: Optional[float] = None
    market_day_high: Optional[float] = None
    market_day_low: Optional[float] = None
    fifty_two_week_high: Optional[float] = None
    fifty_two_week_low: Optional[float] = None
    market_volume: Optional[int] = None
    bid: Optional[float] = None
    bid_size: Optional[int] = None
    ask: Optional[float] = None
    ask_size: Optional[int] = None
    market_cap: Optional[int] = None
    trailing_eps: Optional[float] = None
    forward_eps: Optional[float] = None
    trailing_p_e: Optional[float] = None
    forward_p_e: Optional[float] = None
    beta: Optional[float] = None
    recommendation_key: Optional[str] = None
    target_high_price: Optional[float] = None
    target_low_price: Optional[float] = None
    target_mean_price: Optional[float] = None
    target_median_price: Optional[float] = None

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
            ),
            forward_eps=ticker.info.get("forwardEps"),
            trailing_p_e=ticker.info.get("trailingPE"),
            forward_p_e=ticker.info.get("forwardPE"),
            beta=(ticker.info.get("beta") if ticker.info.get("beta") else ticker.info.get("beta3Year")),
            recommendation_key=ticker.info.get("recommendationKey"),
            target_high_price=ticker.info.get("targetHighPrice"),
            target_low_price=ticker.info.get("targetLowPrice"),
            target_mean_price=ticker.info.get("targetMeanPrice"),
            target_median_price=ticker.info.get("targetMedianPrice"),
        )

    def to_currency(self, currency: str, x_rate: float) -> "StockQuote":
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
    recent_high_price: Optional[float] = None
    pull_pack_percent: Optional[float] = None
    current_volume: Optional[int] = None
    yesterday_volume: Optional[int] = None
    average_volume_30d: Optional[int] = None
    ma10: Optional[float] = None
    ma20: Optional[float] = None
    ma50: Optional[float] = None
    ma100: Optional[float] = None
    ma200: Optional[float] = None
    rsi14: Optional[float] = None
    history_90d: Optional[list[HistoryPoint]] = None

    def __init__(self, ticker: yf.Ticker):
        super().__init__()
        currency = ticker.info.get("currency")
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
        self.ma10 = history365d["Close"].rolling(window=10).mean().iloc[-1]
        self.ma20 = history365d["Close"].rolling(window=20).mean().iloc[-1]
        self.ma50 = history365d["Close"].rolling(window=50).mean().iloc[-1]
        self.ma100 = history365d["Close"].rolling(window=100).mean().iloc[-1]
        self.ma200 = history365d["Close"].rolling(window=200).mean().iloc[-1]

        # calculate Relative Strength Index (RSI)
        delta = history365d["Close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        self.rsi14 = rsi.iloc[-1]

        # store history for 90 days
        num_points = 90
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
    stock_quote: Optional[StockQuote] = None
    dividend: Optional[SymbolDividend] = None
    stock_history: Optional[StockHistory] = None

    def __init__(self, ticker: yf.Ticker):
        super().__init__(
            ticker,
            stock_quote=StockQuote(ticker),
            dividend=SymbolDividend(ticker),
            stock_history=StockHistory(ticker),
        )


# ----------------------------------------------------------------------#


def normalize_json_str(json_str: str) -> str:
    if json_str.startswith("```json"):
        json_str = json_str[len("```json") :].strip()
    if json_str.endswith("```"):
        json_str = json_str[: -len("```")].strip()
    return json_str


class LLMResponse(BaseModel):
    completion: str = ""
    time_taken_ms: int = 0
    tokens_prompt: int = 0
    tokens_completion: int = 0
    tokens_thought: int = 0
    is_error: bool = False


class EventBase(BaseModel):
    symbol: str
    exchange: Optional[str] = None
    company_name: Optional[str] = None
    timestamp: Optional[int] = 0
    date: Optional[str] = None
    event_category: Optional[str] = None
    source_name: Optional[str] = None
    link: Optional[str] = None


class UpcomingDividendEvent(EventBase):
    status: Optional[str] = None
    amount: Optional[float] = None
    dividend_yield: Optional[float] = None
    currency: Optional[str] = None
    payment_date: Optional[str] = None
    analysis: Optional[DividendEventAnalysis] = None


def parse_upcoming_dividend_events_from_json(
    json_str: str, default_vals: dict[str, Any] = None
) -> list[UpcomingDividendEvent]:
    default_vals = default_vals or {}
    json_str = normalize_json_str(json_str)
    events = json.loads(json_str)
    result = []
    for item in events:
        event = UpcomingDividendEvent(
            symbol=item.get("sym", default_vals.get("sym")),
            exchange=item.get("exchange", default_vals.get("exchange")),
            company_name=item.get("corp", default_vals.get("corp")),
            date=item.get("date", default_vals.get("date")),
            payment_date=item.get("pdate", default_vals.get("pdate")),
            event_category=item.get("cat", default_vals.get("cat", "Dividend")),
            source_name=item.get("src", default_vals.get("src")),
            link=item.get("link", default_vals.get("link")),
            status=item.get("status", default_vals.get("status")),
            amount=item.get("amount", default_vals.get("amount")),
            dividend_yield=item.get("yield", default_vals.get("yield")),
            currency=item.get("currency", default_vals.get("currency")),
        )
        # parse yyyy-MM-dd from event.date into event.timestamp
        event.timestamp = int(datetime.strptime(event.date, "%Y-%m-%d").timestamp())
        result.append(event)

    return result


class UpcomingEarningsEvent(EventBase):
    report_period: Optional[str] = None
    status: Optional[str] = None


def parse_upcoming_earnings_events_from_json(
    json_str: str, default_vals: dict[str, Any] = None
) -> list[UpcomingEarningsEvent]:
    json_str = normalize_json_str(json_str)
    events = json.loads(json_str)
    result = []
    for item in events:
        event = UpcomingEarningsEvent(
            symbol=item.get("sym", default_vals.get("sym")),
            exchange=item.get("exchange", default_vals.get("exchange")),
            company_name=item.get("corp", default_vals.get("corp")),
            date=item.get("date", default_vals.get("date")),
            event_category="earnings",
            source_name=item.get("src", default_vals.get("src")),
            link=item.get("link", default_vals.get("link")),
            report_period=item.get("report_period", default_vals.get("report_period")),
            status=item.get("status", default_vals.get("status")),
        )
        # parse yyyy-MM-dd from event.date into event.timestamp
        event.timestamp = int(datetime.strptime(event.date, "%Y-%m-%d").timestamp())
        result.append(event)

    return result


class ListingEvent(EventBase):
    sector: Optional[str] = None
    principal_activities: Optional[str] = None
    price: float = 0.0
    currency: Optional[str] = None
    capital: Optional[int] = None


def parse_new_listing_events_from_json(json_str: str, default_vals: dict[str, Any] = None) -> list[ListingEvent]:
    json_str = normalize_json_str(json_str)
    events = json.loads(json_str)
    result = []
    for item in events:
        event = ListingEvent(
            symbol=item.get("symbol", default_vals.get("symbol")),
            exchange=item.get("exchange", default_vals.get("exchange")),
            company_name=item.get("company", default_vals.get("company")),
            date=item.get("date", default_vals.get("date")),
            event_category="listing",
            source_name=item.get("src", default_vals.get("src")),
            link=item.get("link", default_vals.get("link")),
            sector=item.get("sector", default_vals.get("sector")),
            principal_activities=item.get("principal_activities", default_vals.get("principal_activities")),
            price=item.get("price", default_vals.get("price")),
            currency=item.get("currency", default_vals.get("currency")),
            capital=int(item.get("capital", default_vals.get("capital"))),
        )
        # parse yyyy-MM-dd from event.date into event.timestamp
        event.timestamp = int(datetime.strptime(event.date, "%Y-%m-%d").timestamp())
        result.append(event)

    return result


class DividendEventAnalysis(BaseModel):
    # ===== base info
    overview: Optional[SymbolOverview] = None
    price: Optional[float] = None  # current stock price
    ex_div_date: Optional[str] = None
    ex_div_date_timestamp: Optional[int] = None
    div_amount: Optional[float] = None
    div_yield: Optional[float] = None  # div_amount / price
    # ====== analysis result
    num_samples: Optional[int] = None  # number of historical dividend events used for analysis
    drop_price_min: Optional[float] = None
    drop_price_max: Optional[float] = None
    recovery_probability: Optional[float] = None
    recovery_days_min: Optional[int] = None
    recovery_days_max: Optional[int] = None
    recovery_price_min: Optional[float] = None
    recovery_price_max: Optional[float] = None
    # ===== technical data, used for further analysis with AI
    beta: Optional[float] = None
    rsi14: Optional[int] = None
    avg_dvt_7d: Optional[int] = None
    std_dvt_7d: Optional[int] = None
    avg_volume_30d: Optional[int] = None
    std_volume_30d: Optional[int] = None
    bid_ask_spread: Optional[float] = None
    trend_60d: Optional[float] = None
    market_trend_60d: Optional[float] = None
    peer_trend_60d: Optional[float] = None
    # ====== analysis result from AI
    llm_error: float = False
    llm_error_msg: Optional[str] = None
    search_summary: Optional[str] = None
    strategy: Optional[str] = None
    reasoning: Optional[str] = None
    sentiment_score: Optional[float] = None
    recovery_probability_adj: Optional[float] = None
    recovery_days_adj: Optional[str] = None
    drop_price_adj: Optional[str] = None
    recovery_price_adj: Optional[str] = None
    expected_pl: Optional[float] = None
    confidence_level: Optional[float] = None
    risk_level: Optional[float] = None
