from pydantic import BaseModel
from typing import Any, Optional
import yfinance as yf


class SymbolBase(BaseModel):
    symbol: str
    currency: str
    exchange: str
    raw: Optional[Any] = None
    model_config = {"arbitrary_types_allowed": True}


class SymbolOverview(BaseModel):
    country: Optional[str] = None
    short_name: Optional[str] = None
    long_name: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    website: Optional[str] = None
    description: Optional[str] = None
    quote_type: Optional[str] = None
    model_config = {"arbitrary_types_allowed": True}

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
    model_config = {"arbitrary_types_allowed": True}

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
    model_config = {"arbitrary_types_allowed": True}

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


class SymbolInfo(SymbolBase):
    overview: Optional[SymbolOverview] = None
    stock_quote: Optional[StockQuote] = None
    dividend: Optional[SymbolDividend] = None
    model_config = {"arbitrary_types_allowed": True}

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
        )
