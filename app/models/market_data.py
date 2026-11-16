from __future__ import annotations

import yfinance as yf
from pydantic import BaseModel, Field


class HistoryPoint(BaseModel):
    """One historical market-price observation and derived indicators."""

    timestamp: int = Field(description="Unix timestamp of the market observation.")
    timestamp_str: str = Field(description="Timezone-aware display timestamp.")
    currency: str = Field(
        default="",
        description="Provider or caller-supplied currency identifier for the price values.",
    )
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
        """Return a converted copy of this market observation.

        Args:
            currency: Currency identifier to assign verbatim to the converted
                monetary values.
            x_rate: Exchange rate multiplied by prices, dividends, and daily
                value traded.

        Returns:
            A new history point with monetary values converted. ``None`` and
            zero monetary values are preserved, while volume and RSI remain
            unchanged.
        """
        return self.model_copy(
            update={
                "currency": currency,
                "open": self.open * x_rate,
                "high": self.high * x_rate,
                "low": self.low * x_rate,
                "close": self.close * x_rate,
                "dividends": self.dividends * x_rate if self.dividends is not None else None,
                "dvt": self.dvt * x_rate if self.dvt is not None else None,
            }
        )


class StockQuote(BaseModel):
    """Current quote, valuation, and analyst-target data for a security."""

    currency: str | None = Field(
        default="",
        description="Provider or caller-supplied currency identifier for quote and target prices.",
    )
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
        """Build a quote from Yahoo Finance ticker metadata.

        Args:
            ticker: Ticker whose ``info`` mapping supplies quote, valuation,
                and analyst-target values. Trailing EPS uses ``trailingEps``
                when present and falls back to ``epsTrailingTwelveMonths``.
        """
        info = ticker.info
        trailing_eps = info.get("trailingEps")
        if trailing_eps is None:
            trailing_eps = info.get("epsTrailingTwelveMonths")
        beta = info.get("beta")
        if beta is None:
            beta = info.get("beta3Year")
        super().__init__(
            currency=info.get("currency"),
            market_price=info.get("regularMarketPrice"),
            market_price_change=info.get("regularMarketChange"),
            market_price_change_percent=info.get("regularMarketChangePercent"),
            market_open=info.get("regularMarketOpen"),
            market_day_high=info.get("regularMarketDayHigh"),
            market_day_low=info.get("regularMarketDayLow"),
            fifty_two_week_high=info.get("fiftyTwoWeekHigh"),
            fifty_two_week_low=info.get("fiftyTwoWeekLow"),
            market_volume=info.get("regularMarketVolume"),
            bid=info.get("bid"),
            bid_size=info.get("bidSize"),
            ask=info.get("ask"),
            ask_size=info.get("askSize"),
            market_cap=info.get("marketCap"),
            trailing_eps=trailing_eps,
            forward_eps=info.get("forwardEps"),
            trailing_p_e=info.get("trailingPE"),
            forward_p_e=info.get("forwardPE"),
            beta=beta,
            recommendation_key=info.get("recommendationKey"),
            target_high_price=info.get("targetHighPrice"),
            target_low_price=info.get("targetLowPrice"),
            target_mean_price=info.get("targetMeanPrice"),
            target_median_price=info.get("targetMedianPrice"),
        )

    def to_currency(self, currency: str, x_rate: float) -> StockQuote:
        """Return a converted copy of this quote.

        Args:
            currency: Currency identifier to assign verbatim to the converted
                quote.
            x_rate: Exchange rate multiplied by monetary quote values.

        Returns:
            A new quote with prices, absolute price change, market
            capitalization, earnings per share, and analyst targets converted;
            market capitalization is rounded to the nearest whole currency
            unit. ``None`` and zero monetary values are preserved.
            Percentages, valuation ratios, beta, volumes, sizes, and
            recommendation labels remain unchanged.
        """
        return self.model_copy(
            update={
                "currency": currency,
                "market_price": self.market_price * x_rate if self.market_price is not None else None,
                "market_price_change": (
                    self.market_price_change * x_rate if self.market_price_change is not None else None
                ),
                "market_open": self.market_open * x_rate if self.market_open is not None else None,
                "market_day_high": self.market_day_high * x_rate if self.market_day_high is not None else None,
                "market_day_low": self.market_day_low * x_rate if self.market_day_low is not None else None,
                "fifty_two_week_high": (
                    self.fifty_two_week_high * x_rate if self.fifty_two_week_high is not None else None
                ),
                "fifty_two_week_low": (
                    self.fifty_two_week_low * x_rate if self.fifty_two_week_low is not None else None
                ),
                "bid": self.bid * x_rate if self.bid is not None else None,
                "ask": self.ask * x_rate if self.ask is not None else None,
                "market_cap": round(self.market_cap * x_rate) if self.market_cap is not None else None,
                "trailing_eps": self.trailing_eps * x_rate if self.trailing_eps is not None else None,
                "forward_eps": self.forward_eps * x_rate if self.forward_eps is not None else None,
                "target_high_price": (self.target_high_price * x_rate if self.target_high_price is not None else None),
                "target_low_price": self.target_low_price * x_rate if self.target_low_price is not None else None,
                "target_mean_price": (self.target_mean_price * x_rate if self.target_mean_price is not None else None),
                "target_median_price": (
                    self.target_median_price * x_rate if self.target_median_price is not None else None
                ),
            }
        )
