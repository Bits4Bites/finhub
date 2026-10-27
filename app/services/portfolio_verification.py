from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .. import config
from ..models import portfolio as models_portfolio
from ..utils import cache, conv
from . import stock as services_stock

_CACHE_NAMESPACE = "portfolio-verification-v1"
_SECURITY_QUOTES_CACHE_NAMESPACE = "portfolio-security-quotes-v3"
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


class VerifiedSecurityIdentity(BaseModel):
    """Provider-native and application-canonical identity for one verified security."""

    model_config = ConfigDict(extra="forbid")

    requested_ticker: str
    symbol: str
    ticker: str
    company_name: str | None
    exchange: str
    currency: str = Field(min_length=3, max_length=3)
    quote_type: str


class VerifiedSecurityQuote(VerifiedSecurityIdentity):
    """Verified market data for deterministic whole-share sizing."""

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


@dataclass(frozen=True)
class CandidateIdentityVerification:
    identities: tuple[VerifiedSecurityIdentity, ...]
    rejected_tickers: tuple[str, ...]


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


def verify_candidate_identities(
    tickers: list[str],
    *,
    country: str,
    expected_currency: str,
) -> CandidateIdentityVerification:
    normalized_country = conv.country_to_iso2(country.strip())
    if not normalized_country:
        raise PortfolioInputError("Unsupported or unknown country")
    normalized_currency = expected_currency.strip().upper()
    if len(normalized_currency) != 3:
        raise PortfolioInputError("Expected candidate currency must use a three-letter code")

    try:
        normalized_tickers = [models_portfolio.normalize_canonical_ticker(ticker) for ticker in tickers]
    except ValueError as exc:
        raise PortfolioInputError("Candidate tickers must use EXCHANGE:CODE format") from exc

    identities: list[VerifiedSecurityIdentity] = []
    rejected_tickers: list[str] = []
    seen_tickers: set[str] = set()
    for requested_ticker in normalized_tickers:
        try:
            identity, _ = _load_security_identity(requested_ticker)
            if identity.currency != normalized_currency:
                raise PortfolioInputError(
                    f"Ticker '{identity.ticker}' uses {identity.currency}, not expected {normalized_currency}"
                )
            if identity.ticker in seen_tickers:
                raise PortfolioInputError(f"Ticker '{requested_ticker}' duplicates verified ticker '{identity.ticker}'")
        except (PortfolioInputError, PortfolioVerificationError, ValueError) as exc:
            logging.warning(
                "[Portfolio Verification] Rejected research candidate %s: %s",
                requested_ticker,
                exc,
            )
            rejected_tickers.append(requested_ticker)
            continue
        seen_tickers.add(identity.ticker)
        identities.append(identity)

    return CandidateIdentityVerification(
        identities=tuple(identities),
        rejected_tickers=tuple(rejected_tickers),
    )


def _load_security_identity(
    input_ticker: str,
) -> tuple[VerifiedSecurityIdentity, float | None]:
    try:
        resolved = services_stock.resolve_symbol(input_ticker)
    except Exception as exc:
        raise PortfolioVerificationError(f"Unable to verify ticker '{input_ticker}'") from exc

    if resolved.quote_type not in config.ALLOWED_QUOTE_TYPES:
        raise PortfolioInputError(f"Unsupported or unknown ticker '{input_ticker}'")

    try:
        canonical_ticker = models_portfolio.normalize_canonical_ticker(resolved.normalized_symbol)
    except ValueError as exc:
        raise PortfolioInputError(f"Unable to normalize ticker '{input_ticker}'") from exc
    if not isinstance(canonical_ticker, str):
        raise PortfolioInputError(f"Unable to normalize ticker '{input_ticker}'")

    canonical_exchange = canonical_ticker.split(":", 1)[0]
    if not canonical_exchange:
        raise PortfolioInputError(f"Ticker '{canonical_ticker}' has no exchange")

    if not resolved.currency:
        raise PortfolioInputError(f"Ticker '{canonical_ticker}' has no currency")

    return (
        VerifiedSecurityIdentity(
            requested_ticker=input_ticker.strip().upper(),
            symbol=resolved.symbol,
            ticker=canonical_ticker,
            company_name=resolved.company_name,
            exchange=canonical_exchange,
            currency=resolved.currency,
            quote_type=resolved.quote_type,
        ),
        resolved.market_price,
    )


def _load_security_quote(
    input_ticker: str,
    *,
    fallback_market_price: float | None = None,
) -> tuple[VerifiedSecurityQuote, bool]:
    identity, market_price = _load_security_identity(input_ticker)
    used_fallback = market_price is None and fallback_market_price is not None
    if market_price is None:
        market_price = fallback_market_price
    if market_price is None:
        raise PortfolioInputError(f"Ticker '{identity.ticker}' has no current market price")

    return (
        VerifiedSecurityQuote(
            **identity.model_dump(),
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
