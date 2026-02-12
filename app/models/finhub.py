from pydantic import BaseModel
from typing import Optional
import yfinance as yf


class SymbolBase(BaseModel):
    symbol: str
    currency: str
    exchange: str


class HistoryValueDaily(BaseModel):
    timestamp: int
    value: float


class SymbolOverview(BaseModel):
    country: Optional[str] = None
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

    def __init__(self, ticker: yf.Ticker):
        super().__init__(
            country=ticker.info.get("country"),
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
        )


class SymbolDividend(BaseModel):
    dividend_rate: Optional[float] = None
    dividend_yield: Optional[float] = None
    ex_dividend_date: Optional[int] = None
    five_year_avg_dividend_yield: Optional[float] = None
    trailing_annual_dividend_rate: Optional[float] = None
    trailing_annual_dividend_yield: Optional[float] = None
    last_dividend_value: Optional[float] = None
    last_dividend_date: Optional[int] = None

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


class StockQuote(BaseModel):
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


class StockHistory(BaseModel):
    recent_high_price: Optional[float] = None
    pull_pack_percent: Optional[float] = None
    current_volume: Optional[int] = None
    average_volume_30d: Optional[int] = None
    ma10: Optional[float] = None
    ma20: Optional[float] = None
    ma50: Optional[float] = None
    ma100: Optional[float] = None
    ma200: Optional[float] = None
    rsi14: Optional[float] = None
    rsi14_history_daily: Optional[list[HistoryValueDaily]] = None

    def __init__(self, ticker: yf.Ticker):
        super().__init__()
        history365d = ticker.history(period="365d", interval="1d")
        history30d = history365d.iloc[-30:]

        # calculate pullback if any
        self.recent_high_price = history30d["Close"].iloc[:-2].max()
        current_price = history365d["Close"].iloc[-1]
        self.pull_pack_percent = (
            (self.recent_high_price - current_price) * 100 / self.recent_high_price if self.recent_high_price else 0
        )

        # calculate moving averages
        self.current_volume = int(history365d["Volume"].iloc[-1])
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

        # store RSI history for the last 30 days
        self.rsi14_history_daily = [
            HistoryValueDaily(timestamp=int(history365d.index[-30 + i].timestamp()), value=rsi.iloc[-30 + i])
            for i in range(0, 30)
        ]
        self.rsi14_history_daily.reverse()


class SymbolInfo(SymbolBase):
    overview: Optional[SymbolOverview] = None
    stock_quote: Optional[StockQuote] = None
    dividend: Optional[SymbolDividend] = None
    stock_history: Optional[StockHistory] = None

    def __init__(self, symbol: str, ticker: yf.Ticker):
        super().__init__(
            symbol=symbol,
            currency=ticker.info.get("currency"),
            exchange=(
                ticker.info.get("fullExchangeName")
                if ticker.info.get("fullExchangeName")
                else ticker.info.get("exchange")
            ),
            overview=SymbolOverview(ticker),
            stock_quote=StockQuote(ticker),
            dividend=SymbolDividend(ticker),
            stock_history=StockHistory(ticker),
        )
