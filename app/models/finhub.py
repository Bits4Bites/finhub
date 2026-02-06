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
    country: Optional[str]
    short_name: Optional[str]
    long_name: Optional[str]
    sector: Optional[str]
    industry: Optional[str]
    website: Optional[str]
    description: Optional[str]
    quote_type: Optional[str]
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


class StockQuote(BaseModel):
    market_price: Optional[float]
    model_config = {"arbitrary_types_allowed": True}

    def __init__(self, ticker: yf.Ticker):
        super().__init__(market_price=ticker.info.get("regularMarketPrice"))


class SymbolInfo(SymbolBase):
    overview: Optional[SymbolOverview]
    stock_quote: Optional[StockQuote]
    model_config = {"arbitrary_types_allowed": True}

    def __init__(self, symbol: str, ticker: yf.Ticker):
        super().__init__(
            symbol=symbol,
            currency=ticker.info.get("currency"),
            exchange=ticker.info.get("exchange"),
            overview=SymbolOverview(ticker),
            stock_quote=StockQuote(ticker),
        )
