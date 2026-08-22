from __future__ import annotations

import json
import math
from datetime import UTC, datetime

import yfinance as yf
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .. import config
from ..models import portfolio as models_portfolio
from ..utils import cache, conv

_CACHE_NAMESPACE = "portfolio-verification-v1"
_CACHE_TTL = 5 * 60


class PortfolioInputError(ValueError):
    pass


class PortfolioVerificationError(RuntimeError):
    pass


class VerifiedPortfolio(BaseModel):
    model_config = ConfigDict(extra="forbid")

    as_of: datetime
    country: str = Field(min_length=2, max_length=2)
    currency: str = Field(min_length=3, max_length=3)
    total_market_value: float = Field(gt=0, allow_inf_nan=False)
    holdings: list[models_portfolio.PortfolioVerifiedHolding] = Field(min_length=1, max_length=50)
    data_gaps: list[str] = Field(max_length=20)

    @model_validator(mode="after")
    def validate_portfolio(self) -> VerifiedPortfolio:
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("verified portfolio as_of must be timezone-aware")
        tickers = [holding.ticker for holding in self.holdings]
        if len(tickers) != len(set(tickers)):
            raise ValueError("verified portfolio holding tickers must be unique")
        allocation_total = sum(holding.current_allocation for holding in self.holdings)
        if abs(allocation_total - 1.0) > 1e-6:
            raise ValueError("verified portfolio current allocations must sum to one")
        return self


async def verify_portfolio(
    portfolio: list[models_portfolio.PortfolioHolding],
    *,
    country: str,
) -> VerifiedPortfolio:
    serialized_positions = json.dumps(
        [position.model_dump(mode="json") for position in sorted(portfolio, key=lambda position: position.ticker)],
        sort_keys=True,
    )
    cache_key = cache.generate_key(
        _CACHE_NAMESPACE,
        country,
        serialized_positions,
    )
    cached_portfolio = await cache.get(cache_key)
    if cached_portfolio is not None:
        return _cached_portfolio(cached_portfolio)

    verified_portfolio = _build_verified_portfolio(portfolio, country=country)
    await cache.set(
        cache_key,
        verified_portfolio.model_dump(mode="json"),
        ttl=_CACHE_TTL,
    )
    return verified_portfolio


def _build_verified_portfolio(
    portfolio: list[models_portfolio.PortfolioHolding],
    *,
    country: str,
) -> VerifiedPortfolio:
    if not portfolio:
        raise PortfolioInputError("Portfolio must contain at least one positive-share position")

    verified_data: list[dict[str, object]] = []
    data_gaps: list[str] = []
    seen_tickers: set[str] = set()
    currencies: set[str] = set()

    for position in sorted(portfolio, key=lambda item: item.ticker):
        if position.num_shares <= 0:
            raise PortfolioInputError("Portfolio verification requires positive-share positions")

        yf_symbol = conv.to_yf_symbol_format(position.ticker)
        try:
            ticker = yf.Ticker(yf_symbol)
            info = ticker.info or {}
        except Exception as exc:
            raise PortfolioVerificationError(f"Unable to verify ticker '{position.ticker}'") from exc

        quote_type = str(info.get("quoteType") or "").upper()
        if quote_type not in config.ALLOWED_QUOTE_TYPES:
            raise PortfolioInputError(f"Unsupported or unknown ticker '{position.ticker}'")

        canonical_ticker = conv.to_exch_symb_format(ticker=ticker).strip().upper()
        if not canonical_ticker or canonical_ticker.startswith(":") or canonical_ticker.endswith(":"):
            raise PortfolioInputError(f"Unable to normalize ticker '{position.ticker}'")
        if canonical_ticker in seen_tickers:
            raise PortfolioInputError(f"Duplicate portfolio ticker '{canonical_ticker}'")
        seen_tickers.add(canonical_ticker)

        exchange = conv.normalize_exchange_code(str(info.get("fullExchangeName") or info.get("exchange") or ""))
        if not exchange:
            raise PortfolioInputError(f"Ticker '{canonical_ticker}' has no exchange")

        currency = str(info.get("currency") or "").strip().upper()
        if not currency:
            raise PortfolioInputError(f"Ticker '{canonical_ticker}' has no currency")
        currencies.add(currency)

        market_price = _positive_finite_number(info.get("regularMarketPrice"))
        if market_price is None:
            market_price = _positive_finite_number(info.get("currentPrice"))
        if market_price is not None:
            price_source: models_portfolio.PortfolioPriceSource = "MarketData"
        elif position.market_price is not None:
            market_price = position.market_price
            price_source = "Client"
            data_gaps.append(
                f"Used the client-supplied market price for {canonical_ticker} because current market data was unavailable."
            )
        else:
            raise PortfolioInputError(f"Ticker '{canonical_ticker}' has no current market price")

        verified_data.append(
            {
                "ticker": canonical_ticker,
                "company_name": str(info.get("longName") or info.get("shortName") or "").strip() or None,
                "exchange": exchange,
                "currency": currency,
                "num_shares": position.num_shares,
                "avg_price": position.avg_price,
                "market_price": market_price,
                "price_source": price_source,
                "market_value": position.num_shares * market_price,
                "target_allocation": position.target_allocation,
                "tags": position.tags,
            }
        )

    if len(currencies) != 1:
        raise PortfolioInputError("Mixed-currency portfolios are not supported")

    total_market_value = sum(float(holding["market_value"]) for holding in verified_data)
    if not math.isfinite(total_market_value) or total_market_value <= 0:
        raise PortfolioInputError("Portfolio market value must be positive")

    holdings = []
    for holding in verified_data:
        current_allocation = float(holding["market_value"]) / total_market_value
        target_allocation = holding["target_allocation"]
        avg_price = float(holding["avg_price"])
        num_shares = float(holding["num_shares"])
        market_price = float(holding["market_price"])
        holdings.append(
            models_portfolio.PortfolioVerifiedHolding(
                **holding,
                current_allocation=current_allocation,
                allocation_drift=(
                    current_allocation - float(target_allocation) if target_allocation is not None else None
                ),
                unrealized_profit_loss=((market_price - avg_price) * num_shares if avg_price > 0 else None),
            )
        )

    return VerifiedPortfolio(
        as_of=datetime.now(UTC),
        country=country,
        currency=next(iter(currencies)),
        total_market_value=total_market_value,
        holdings=holdings,
        data_gaps=list(dict.fromkeys(data_gaps))[:20],
    )


def _positive_finite_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    number = float(value)
    return number if math.isfinite(number) and number > 0 else None


def _cached_portfolio(value: object) -> VerifiedPortfolio:
    try:
        return (
            value.model_copy(deep=True)
            if isinstance(value, VerifiedPortfolio)
            else VerifiedPortfolio.model_validate(value)
        )
    except (TypeError, ValidationError) as exc:
        raise RuntimeError("Portfolio verification cache contains an invalid value") from exc
