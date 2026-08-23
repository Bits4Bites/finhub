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
_SECURITY_QUOTES_CACHE_NAMESPACE = "portfolio-security-quotes-v1"
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


class VerifiedSecurityQuote(BaseModel):
    """Verified market data for deterministic whole-share sizing."""

    model_config = ConfigDict(extra="forbid")

    ticker: str
    company_name: str | None
    exchange: str
    currency: str = Field(min_length=3, max_length=3)
    market_price: float = Field(gt=0, allow_inf_nan=False)


class VerifiedSecurityQuotes(BaseModel):
    """A same-currency collection of verified target-security quotes."""

    model_config = ConfigDict(extra="forbid")

    as_of: datetime
    country: str = Field(min_length=2, max_length=2)
    currency: str = Field(min_length=3, max_length=3)
    securities: list[VerifiedSecurityQuote] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def validate_quotes(self) -> VerifiedSecurityQuotes:
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("verified security quotes as_of must be timezone-aware")
        tickers = [security.ticker for security in self.securities]
        if len(tickers) != len(set(tickers)):
            raise ValueError("verified security quote tickers must be unique")
        if {security.currency for security in self.securities} != {self.currency}:
            raise ValueError("verified security quotes must use the declared currency")
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


async def verify_security_quotes(
    tickers: list[str],
    *,
    country: str,
) -> VerifiedSecurityQuotes:
    """Verify target-security prices without creating synthetic portfolio holdings."""
    if not tickers:
        raise PortfolioInputError("At least one target-security ticker is required")
    normalized_country = conv.country_to_iso2(country.strip())
    if not normalized_country:
        raise PortfolioInputError("Unsupported or unknown country")
    try:
        normalized_tickers = [models_portfolio.normalize_canonical_ticker(ticker) for ticker in tickers]
    except ValueError as exc:
        raise PortfolioInputError("Target-security tickers must use EXCHANGE:CODE format") from exc
    if len(normalized_tickers) != len(set(normalized_tickers)):
        raise PortfolioInputError("Target-security tickers must be unique")

    cache_key = cache.generate_key(
        _SECURITY_QUOTES_CACHE_NAMESPACE,
        normalized_country,
        json.dumps(sorted(normalized_tickers)),
    )
    cached_quotes = await cache.get(cache_key)
    if cached_quotes is not None:
        return _cached_security_quotes(cached_quotes)

    verified_quotes = _build_verified_security_quotes(
        normalized_tickers,
        country=normalized_country,
    )
    await cache.set(
        cache_key,
        verified_quotes.model_dump(mode="json"),
        ttl=_CACHE_TTL,
    )
    return verified_quotes


def _load_security_quote(
    input_ticker: str,
    *,
    fallback_market_price: float | None = None,
) -> tuple[VerifiedSecurityQuote, bool]:
    yf_symbol = conv.to_yf_symbol_format(input_ticker)
    try:
        ticker = yf.Ticker(yf_symbol)
        info = ticker.info or {}
    except Exception as exc:
        raise PortfolioVerificationError(f"Unable to verify ticker '{input_ticker}'") from exc

    quote_type = str(info.get("quoteType") or "").upper()
    if quote_type not in config.ALLOWED_QUOTE_TYPES:
        raise PortfolioInputError(f"Unsupported or unknown ticker '{input_ticker}'")

    canonical_ticker = conv.to_exch_symb_format(ticker=ticker).strip().upper()
    if not canonical_ticker or canonical_ticker.startswith(":") or canonical_ticker.endswith(":"):
        raise PortfolioInputError(f"Unable to normalize ticker '{input_ticker}'")

    exchange = conv.normalize_exchange_code(str(info.get("fullExchangeName") or info.get("exchange") or ""))
    if not exchange:
        raise PortfolioInputError(f"Ticker '{canonical_ticker}' has no exchange")

    currency = str(info.get("currency") or "").strip().upper()
    if not currency:
        raise PortfolioInputError(f"Ticker '{canonical_ticker}' has no currency")

    market_price = _positive_finite_number(info.get("regularMarketPrice"))
    if market_price is None:
        market_price = _positive_finite_number(info.get("currentPrice"))
    used_fallback = market_price is None and fallback_market_price is not None
    if market_price is None:
        market_price = fallback_market_price
    if market_price is None:
        raise PortfolioInputError(f"Ticker '{canonical_ticker}' has no current market price")

    return (
        VerifiedSecurityQuote(
            ticker=canonical_ticker,
            company_name=str(info.get("longName") or info.get("shortName") or "").strip() or None,
            exchange=exchange,
            currency=currency,
            market_price=market_price,
        ),
        used_fallback,
    )


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

        quote, used_fallback = _load_security_quote(
            position.ticker,
            fallback_market_price=position.market_price,
        )
        canonical_ticker = quote.ticker
        if canonical_ticker in seen_tickers:
            raise PortfolioInputError(f"Duplicate portfolio ticker '{canonical_ticker}'")
        seen_tickers.add(canonical_ticker)
        currencies.add(quote.currency)
        if used_fallback:
            price_source: models_portfolio.PortfolioPriceSource = "Client"
            data_gaps.append(
                f"Used the client-supplied market price for {canonical_ticker} because current market data was unavailable."
            )
        else:
            price_source = "MarketData"

        verified_data.append(
            {
                "ticker": canonical_ticker,
                "company_name": quote.company_name,
                "exchange": quote.exchange,
                "currency": quote.currency,
                "num_shares": position.num_shares,
                "avg_price": position.avg_price,
                "market_price": quote.market_price,
                "price_source": price_source,
                "market_value": position.num_shares * quote.market_price,
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


def _build_verified_security_quotes(
    tickers: list[str],
    *,
    country: str,
) -> VerifiedSecurityQuotes:
    securities: list[VerifiedSecurityQuote] = []
    seen_tickers: set[str] = set()
    currencies: set[str] = set()
    for ticker in sorted(tickers):
        quote, _ = _load_security_quote(ticker)
        if quote.ticker in seen_tickers:
            raise PortfolioInputError(f"Duplicate target-security ticker '{quote.ticker}'")
        seen_tickers.add(quote.ticker)
        currencies.add(quote.currency)
        securities.append(quote)

    if len(currencies) != 1:
        raise PortfolioInputError("Mixed-currency target portfolios are not supported")
    return VerifiedSecurityQuotes(
        as_of=datetime.now(UTC),
        country=country,
        currency=next(iter(currencies)),
        securities=securities,
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


def _cached_security_quotes(value: object) -> VerifiedSecurityQuotes:
    try:
        return (
            value.model_copy(deep=True)
            if isinstance(value, VerifiedSecurityQuotes)
            else VerifiedSecurityQuotes.model_validate(value)
        )
    except (TypeError, ValidationError) as exc:
        raise RuntimeError("Portfolio security quote cache contains an invalid value") from exc
