from __future__ import annotations

import json
import statistics
from datetime import UTC, datetime
from typing import Any

import pandas as pd
import yfinance as yf
from pydantic import BaseModel

from ..utils import finhub as finhub_utils
from .types import (
    CRYPTO_ASSET,
    ETF_ASSET,
    HYBRID_ASSET,
    LIC_ASSET,
    MUTUAL_FUND_ASSET,
    OTHER_ASSET,
    REIT_ASSET,
    STANDARD_ASSET,
    AssetType,
    MarketCapType,
)


class AIVendorInfo(BaseModel):
    name: str = ""
    tier_models: dict[str, list[str]] = {}  # map {tier -> list of models}


# ----------------------------------------------------------------------#


class SymbolBase(BaseModel):
    symbol: str
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
        self.country = finhub_utils.country_to_iso2(self.country)
        self.exchange = finhub_utils.normalize_exchange_code(self.exchange)


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
    short_name: str = ""
    long_name: str = ""
    sector: str = ""
    industry: str = ""
    website: str = ""
    description: str = ""
    quote_type: str = ""
    asset_type: AssetType | None = None
    total_cash: int = 0
    total_cash_per_share: float = 0.0
    total_debt: int = 0
    total_debt_per_share: float = 0.0
    total_revenue: int = 0
    total_revenue_per_share: float = 0.0
    ebitda: int = 0
    ebitda_margins: float = 0.0
    earnings_growth: float = 0.0
    revenue_growth: float = 0.0
    gross_margins: float = 0.0
    operating_margins: float = 0.0
    profit_margins: float = 0.0
    market_cap: int = 0
    cap_size: MarketCapType | None = None
    market_index: str | None = None

    def __init__(self, ticker: yf.Ticker, /, **data: Any):
        super().__init__(
            ticker,
            short_name=ticker.info.get("shortName", ""),
            long_name=ticker.info.get("longName", ""),
            sector=ticker.info.get("sector", ""),
            industry=ticker.info.get("industry", ""),
            website=ticker.info.get("website", ""),
            description=ticker.info.get("longBusinessSummary", ""),
            quote_type=ticker.info.get("quoteType", ""),
            total_cash=ticker.info.get("totalCash", 0),
            total_cash_per_share=ticker.info.get("totalCashPerShare", 0.0),
            total_debt=ticker.info.get("totalDebt", 0),
            total_debt_per_share=ticker.info.get("totalDebtPerShare", 0.0),
            total_revenue=ticker.info.get("totalRevenue", 0),
            total_revenue_per_share=ticker.info.get("totalRevenuePerShare", 0.0),
            ebitda=ticker.info.get("ebitda", 0),
            ebitda_margins=ticker.info.get("ebitdaMargins", 0.0),
            earnings_growth=ticker.info.get("earningsGrowth", 0.0),
            revenue_growth=ticker.info.get("revenueGrowth", 0.0),
            gross_margins=ticker.info.get("grossMargins", 0.0),
            operating_margins=ticker.info.get("operatingMargins", 0.0),
            profit_margins=ticker.info.get("profitMargins", 0.0),
            market_cap=ticker.info.get("marketCap", 0),
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
        self.cap_size, self.market_index = finhub_utils.classify_market_cap(ticker)

        # detect asset type
        match self.quote_type:
            case "ETF":
                self.asset_type = ETF_ASSET
            case "MUTUALFUND":
                self.asset_type = MUTUAL_FUND_ASSET
            case "CRYPTOCURRENCY":
                self.asset_type = CRYPTO_ASSET
            case "EQUITY":
                self.asset_type = STANDARD_ASSET
                sector = self.sector.upper() if self.sector else ""
                industry = self.industry.upper() if self.industry else ""
                name = self.long_name or self.short_name or ""
                if sector == "REAL ESTATE" and "REIT" in industry:
                    self.asset_type = REIT_ASSET
                elif "ASSET MANAGEMENT" in industry or "Investment" in name:
                    self.asset_type = LIC_ASSET
                elif "Note" in name or "Hybrid" in name:
                    self.asset_type = HYBRID_ASSET
            case "_":
                self.asset_type = OTHER_ASSET


class SymbolDividend(BaseModel):
    dividend_rate: float = 0.0
    dividend_yield: float = 0.0
    payout_frequency: int = 0
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
            dividend_rate=ticker.info.get("dividendRate", 0.0),
            dividend_yield=ticker.info.get("dividendYield", 0.0),
            ex_dividend_date=ticker.info.get("exDividendDate", 0),
            five_year_avg_dividend_yield=ticker.info.get("fiveYearAvgDividendYield", 0.0),
            trailing_annual_dividend_rate=ticker.info.get("trailingAnnualDividendRate", 0.0),
            trailing_annual_dividend_yield=ticker.info.get("trailingAnnualDividendYield", 0.0),
            last_dividend_value=ticker.info.get("lastDividendValue", 0),
            last_dividend_date=ticker.info.get("lastDividendDate", 0.0),
        )
        symbol = ticker.info.get("symbol", "")
        tz = finhub_utils.tz_from_yf_ticker(symbol)
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
    market_price_change: float = 0.0
    market_price_change_percent: float = 0.0
    market_open: float = 0.0
    market_day_high: float = 0.0
    market_day_low: float = 0.0
    fifty_two_week_high: float = 0.0
    fifty_two_week_low: float = 0.0
    market_volume: int = 0
    bid: float = 0.0
    bid_size: int = 0
    ask: float = 0.0
    ask_size: int = 0
    market_cap: int = 0
    trailing_eps: float = 0.0
    forward_eps: float = 0.0
    trailing_p_e: float = 0.0
    forward_p_e: float = 0.0
    beta: float = 0.0
    recommendation_key: str | None = None
    target_high_price: float = 0.0
    target_low_price: float = 0.0
    target_mean_price: float = 0.0
    target_median_price: float = 0.0

    def __init__(self, ticker: yf.Ticker):
        super().__init__(
            currency=ticker.info.get("currency", ""),
            market_price=ticker.info.get("regularMarketPrice", 0.0),
            market_price_change=ticker.info.get("regularMarketChange", 0.0),
            market_price_change_percent=ticker.info.get("regularMarketChangePercent", 0.0),
            market_open=ticker.info.get("regularMarketOpen", 0.0),
            market_day_high=ticker.info.get("regularMarketDayHigh", 0.0),
            market_day_low=ticker.info.get("regularMarketDayLow", 0.0),
            fifty_two_week_high=ticker.info.get("fiftyTwoWeekHigh", 0.0),
            fifty_two_week_low=ticker.info.get("fiftyTwoWeekLow", 0.0),
            market_volume=ticker.info.get("regularMarketVolume", 0),
            bid=ticker.info.get("bid", 0.0),
            bid_size=ticker.info.get("bidSize", 0),
            ask=ticker.info.get("ask", 0.0),
            ask_size=ticker.info.get("askSize", 0),
            market_cap=ticker.info.get("marketCap", 0),
            trailing_eps=(
                ticker.info.get("trailingEps")
                if ticker.info.get("trailingEPS")
                else ticker.info.get("epsTrailingTwelveMonths")
                if ticker.info.get("epsTrailingTwelveMonths")
                else 0.0
            ),
            forward_eps=ticker.info.get("forwardEps", 0.0),
            trailing_p_e=ticker.info.get("trailingPE", 0.0),
            forward_p_e=ticker.info.get("forwardPE", 0.0),
            beta=ticker.info.get("beta") if ticker.info.get("beta") else ticker.info.get("beta3Year", 0.0),
            recommendation_key=ticker.info.get("recommendationKey"),
            target_high_price=ticker.info.get("targetHighPrice", 0.0),
            target_low_price=ticker.info.get("targetLowPrice", 0.0),
            target_mean_price=ticker.info.get("targetMeanPrice", 0.0),
            target_median_price=ticker.info.get("targetMedianPrice", 0.0),
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
    pull_pack_percent: float = 0.0
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


def normalize_json_str(json_str: str) -> str:
    if json_str.startswith("```json"):
        json_str = json_str[len("```json") :].strip()
    if json_str.endswith("```"):
        json_str = json_str[: -len("```")].strip()
    return json_str


# ----------------------------------------------------------------------#


class LLMResponse(BaseModel):
    completion: str = ""
    time_taken_ms: int = 0
    tokens_prompt: int = 0
    tokens_completion: int = 0
    tokens_thought: int = 0
    is_error: bool = False
    error_msg: str | None = None


# ----------------------------------------------------------------------#


class EventBase(BaseModel):
    symbol: str
    exchange: str | None = None
    company_name: str | None = None
    timestamp: int = 0
    date: str | None = None
    event_category: str | None = None
    source_name: str | None = None
    link: str | None = None


class UpcomingDividendEvent(EventBase):
    status: str = ""
    amount: float = 0.0
    dividend_yield: float = 0.0
    currency: str = ""
    payment_date: str | None
    analysis: DividendEventAnalysis | None = None


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
            amount=item.get("amount", default_vals.get("amount", 0.0)),
            dividend_yield=item.get("yield", default_vals.get("yield", 0.0)),
            currency=item.get("currency", default_vals.get("currency", "")),
        )
        # parse yyyy-MM-dd from event.date into event.timestamp
        event.timestamp = int(datetime.strptime(event.date or "", "%Y-%m-%d").timestamp())
        result.append(event)

    return result


class UpcomingEarningsEvent(EventBase):
    report_period: str | None = None
    status: str | None = None


def parse_upcoming_earnings_events_from_json(
    json_str: str, default_vals: dict[str, Any] = None
) -> list[UpcomingEarningsEvent]:
    default_vals = default_vals or {}
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
        event.timestamp = int(datetime.strptime(event.date or "", "%Y-%m-%d").timestamp())
        result.append(event)

    return result


class ListingOutlook(BaseModel):
    direction: str | None = None
    reason: str | None = None
    confidence: int = 0


class ListingAnalysis(BaseModel):
    status: str | None = None
    data_quality: str | None = None
    search_findings: str | None = None
    stance: str | None = None
    catalyst: str | None = None
    risks: list[str] | None = None
    outlook: dict[str, ListingOutlook] | None = None


def parse_listing_analysis_from_json(json_str: str, default_vals: dict[str, Any] = None) -> dict[str, ListingAnalysis]:
    default_vals = default_vals or {}
    json_str = normalize_json_str(json_str)
    analysis = json.loads(json_str)
    result = {}
    for k, v in analysis.items():
        result[k] = ListingAnalysis(
            status=v.get("status", default_vals.get("status")),
            data_quality=v.get("data_quality", default_vals.get("data_quality")),
            search_findings=v.get("search_findings", default_vals.get("search_findings")),
            stance=v.get("stance", default_vals.get("stance")),
            catalyst=v.get("catalyst", default_vals.get("catalyst")),
            risks=v.get("risks", default_vals.get("risks")),
        )
        if "outlook" in v:
            result[k].outlook = {}
            if "w2" in v["outlook"]:
                result[k].outlook["w2"] = ListingOutlook(
                    direction=v["outlook"]["w2"].get("dir"),
                    reason=v["outlook"]["w2"].get("reason"),
                    confidence=v["outlook"]["w2"].get("confidence"),
                )
            if "m1" in v["outlook"]:
                result[k].outlook["m1"] = ListingOutlook(
                    direction=v["outlook"]["m1"].get("dir"),
                    reason=v["outlook"]["m1"].get("reason"),
                    confidence=v["outlook"]["m1"].get("confidence"),
                )
            if "m3" in v["outlook"]:
                result[k].outlook["m3"] = ListingOutlook(
                    direction=v["outlook"]["m3"].get("dir"),
                    reason=v["outlook"]["m3"].get("reason"),
                    confidence=v["outlook"]["m3"].get("confidence"),
                )

    return result


class ListingEvent(EventBase):
    sector: str | None = None
    industry: str | None = None
    principal_activities: str | None = None
    price: float = 0.0
    currency: str = ""
    capital: int = 0
    analysis: ListingAnalysis | None = None


def parse_new_listing_events_from_json(json_str: str, default_vals: dict[str, Any] = None) -> list[ListingEvent]:
    default_vals = default_vals or {}
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
            price=item.get("price", default_vals.get("price", 0.0)),
            currency=item.get("currency", default_vals.get("currency", "")),
            capital=int(item.get("capital", default_vals.get("capital", 0))),
        )
        # parse yyyy-MM-dd from event.date into event.timestamp
        event.timestamp = int(datetime.strptime(event.date or "", "%Y-%m-%d").timestamp())
        result.append(event)

    return result


# ----------------------------------------------------------------------#


class BaseAIResult(BaseModel):
    llm_error: bool = False
    llm_error_msg: str | None = None
    llm_response: str | None = None


class DividendEventAnalysis(BaseAIResult):
    # ===== base info
    overview: SymbolOverview = None
    price: float = 0.0  # current stock price
    ex_div_date: str | None = None
    ex_div_date_timestamp: int = 0
    div_amount: float = 0.0
    div_yield: float = 0.0  # div_amount / price
    # ====== analysis result
    num_samples: int = 0  # number of historical dividend events used for analysis
    drop_price_min: float = 0.0
    drop_price_max: float = 0.0
    recovery_probability: float = 0.0
    recovery_days_min: int = 0
    recovery_days_max: int = 0
    recovery_price_min: float = 0.0
    recovery_price_max: float = 0.0
    # ===== technical data, used for further analysis with AI
    beta: float = 0.0
    rsi14: int = 0
    avg_dvt_7d: int = 0
    std_dvt_7d: int = 0
    avg_volume_30d: int = 0
    std_volume_30d: int = 0
    bid_ask_spread: float = 0.0
    trend_60d: float = 0.0
    market_trend_60d: float = 0.0
    peer_trend_60d: float = 0.0
    # ====== analysis result from AI
    search_summary: str | None = None
    strategy: str | None = None
    reasoning: str | None = None
    sentiment_score: float = 0.0
    recovery_probability_adj: float = 0.0
    recovery_days_adj: str | None = None
    drop_price_adj: str | None = None
    recovery_price_adj: str | None = None
    expected_pl: float = 0.0
    confidence_level: float = 0.0
    risk_level: float = 0.0


class HoldingTicker(BaseModel):
    ticker: str = ""
    num_shares: float = 0.0
    avg_price: float = 0.0
    market_price: float = 0.0
    target_allocation: float = 0.0


class PortfolioAnalysis(BaseAIResult):
    analysis: str = ""
