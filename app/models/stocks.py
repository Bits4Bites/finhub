from __future__ import annotations

import statistics
from datetime import datetime
from typing import Any

import pandas as pd
import yfinance as yf
from pydantic import BaseModel, Field, field_validator

from ..utils import asset as asset_utils
from ..utils import conv, yfutils
from . import market_data as models_market_data
from . import portfolio as models_portfolio
from . import types


class SymbolBase(BaseModel):
    """Canonical identity and market metadata shared by symbol models.

    The constructor trims and uppercases symbol identifiers, canonicalizes
    recognized exchange aliases, converts the provider country to an ISO
    alpha-2 code, and requires an exchange-qualified normalized symbol.
    """

    symbol: types.NonEmptyString = Field(description="Trimmed, uppercase provider-native security symbol.")
    normalized_symbol: str = Field(
        min_length=1,
        description="Canonical EXCHANGE:CODE symbol with a normalized exchange prefix.",
    )
    currency: types.CurrencyCode = Field(
        description="Three-letter trading currency code, trimmed and uppercased from provider metadata."
    )
    exchange: types.NonEmptyString = Field(description="Normalized uppercase exchange code.")
    country: types.CountryCode = Field(description="ISO 3166-1 alpha-2 market country code.")

    @field_validator("normalized_symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: object) -> object:
        return models_portfolio.normalize_canonical_ticker(value)

    def __init__(self, ticker: yf.Ticker, /, **data: Any):
        """Build normalized symbol identity from Yahoo Finance metadata.

        Args:
            ticker: Ticker providing symbol, currency, exchange, and country
                metadata.
            **data: Additional validated fields required by a subclass.
        """
        info = ticker.info
        symbol = str(info.get("symbol") or "").strip().upper()
        exchange = conv.normalize_exchange_code(str(info.get("fullExchangeName") or info.get("exchange") or ""))
        country = conv.country_to_iso2(info.get("country") or info.get("region") or "US")
        normalized_symbol = conv.to_exch_symb_format(ticker=ticker)
        super().__init__(
            symbol=symbol,
            normalized_symbol=normalized_symbol,
            currency=info.get("currency"),
            exchange=exchange,
            country=country,
            **data,
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
        """Build a company overview from Yahoo Finance metadata.

        Args:
            ticker: Ticker providing company, financial, and classification
                metadata.
            **data: Additional validated fields required by a subclass.
        """
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
        description="Provider-reported forward annual dividend yield.",
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
        """Build dividend attributes from ticker metadata and daily history.

        Args:
            ticker: Ticker providing dividend metadata, exchange information,
                and trailing daily history.

        Notes:
            Timestamp display values represent the same Unix instant in the
            exchange timezone. Payout frequency counts positive dividend
            observations in the trailing calendar year.
        """
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
            self.ex_dividend_date_str = datetime.fromtimestamp(
                self.ex_dividend_date,
                tz=tz,
            ).isoformat(sep=" ", timespec="seconds")
        if self.last_dividend_date:
            self.last_dividend_date_str = datetime.fromtimestamp(
                self.last_dividend_date,
                tz=tz,
            ).isoformat(sep=" ", timespec="seconds")

        # calculate payout frequency
        history365d = ticker.history(period="365d", interval="1d", auto_adjust=False)
        idx = history365d.index[-1] - pd.Timedelta(days=365)
        self.payout_frequency = int((history365d[idx:]["Dividends"] > 0).sum())


class StockHistory(BaseModel):
    """Recent price history and derived technical indicators."""

    recent_high_price: float = Field(
        default=0.0,
        description="Highest closing price in the latest 30 daily trading observations.",
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
        description="Average volume across the latest 30 daily trading observations.",
    )
    ma10: float = Field(default=0.0, description="Ten-day simple moving average.")
    ma20: float = Field(default=0.0, description="Twenty-day simple moving average.")
    ma50: float = Field(default=0.0, description="Fifty-day simple moving average.")
    ma100: float = Field(default=0.0, description="One-hundred-day simple moving average.")
    ma200: float = Field(default=0.0, description="Two-hundred-day simple moving average.")
    rsi14: float = Field(default=0.0, description="Fourteen-period relative strength index.")
    history_90d: list[models_market_data.HistoryPoint] = Field(
        default=[],
        description="Up to 90 latest daily trading observations when at least 30 are available.",
    )

    def __init__(self, ticker: yf.Ticker):
        """Build recent technical history from daily Yahoo Finance observations.

        Args:
            ticker: Ticker providing at least 30 daily unadjusted price and
                volume observations from the trailing 365 calendar days.

        Notes:
            Thirty-observation statistics use trading observations rather than
            calendar days, and retained history contains at most the latest 90
            observations.
        """
        super().__init__()
        currency = str(ticker.info.get("currency") or "").strip().upper()
        history365d = ticker.history(period="365d", interval="1d", auto_adjust=False)
        history30d = history365d.iloc[-30:]

        # calculate pullback if any
        self.recent_high_price = history30d["Close"].max()
        current_price = history365d["Close"].iloc[-1]
        self.pull_pack_percent = (
            (self.recent_high_price - current_price) * 100 / self.recent_high_price if self.recent_high_price else 0
        )

        # calculate moving averages
        self.current_volume = int(history365d["Volume"].iloc[-1])
        self.yesterday_volume = int(history365d["Volume"].iloc[-2])
        self.average_volume_30d = int(history30d["Volume"].mean())
        for field_name, window in (
            ("ma10", 10),
            ("ma20", 20),
            ("ma50", 50),
            ("ma100", 100),
            ("ma200", 200),
        ):
            value = history365d["Close"].rolling(window=window).mean().iloc[-1]
            setattr(self, field_name, 0.0 if pd.isna(value) else value)

        # calculate Relative Strength Index (RSI)
        delta = history365d["Close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        self.rsi14 = rsi.iloc[-1]

        # store history for 90 days
        if len(history365d) >= 30:
            num_points = min(90, len(history365d))
            self.history_90d = [
                models_market_data.HistoryPoint(
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

    stock_quote: models_market_data.StockQuote = Field(description="Current quote and valuation data.")
    dividend: SymbolDividend = Field(description="Current and historical dividend attributes.")
    stock_history: StockHistory = Field(description="Recent history and technical indicators.")

    def __init__(self, ticker: yf.Ticker):
        """Build a comprehensive symbol profile from one Yahoo Finance ticker.

        Args:
            ticker: Ticker used to build the overview, current quote, dividend
                attributes, and recent technical history.
        """
        super().__init__(
            ticker,
            stock_quote=models_market_data.StockQuote(ticker),
            dividend=SymbolDividend(ticker),
            stock_history=StockHistory(ticker),
        )
