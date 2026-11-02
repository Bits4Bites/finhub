from __future__ import annotations

import yfinance as yf
from pydantic import BaseModel, Field


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
