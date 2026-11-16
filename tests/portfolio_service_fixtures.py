from __future__ import annotations

import copy
import json
import re
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from app.services import ai_helper
from app.services import stock as services_stock

PORTFOLIO_ID = "$PORTFOLIO_ID"


@dataclass(frozen=True)
class _ActionReasoning:
    pass


ACTION_REASONING = _ActionReasoning()


@dataclass(frozen=True)
class AIResponse:
    data: dict[str, Any]
    citation_urls: tuple[str, ...] = ()


@dataclass
class _CacheEntry:
    value: object
    expires_at: float | None


class MemoryCache:
    def __init__(self) -> None:
        self._values: dict[str, _CacheEntry] = {}
        self._last_key: str | None = None
        self._now = 0.0

    async def get(self, key: str, default: object = None) -> object:
        entry = self._values.get(key)
        if entry is None:
            return copy.deepcopy(default)
        if entry.expires_at is not None and entry.expires_at <= self._now:
            del self._values[key]
            return copy.deepcopy(default)
        return copy.deepcopy(entry.value)

    async def set(self, key: str, value: object, ttl: float = 0) -> bool:
        expires_at = self._now + ttl if ttl > 0 else None
        self._values[key] = _CacheEntry(
            value=copy.deepcopy(value),
            expires_at=expires_at,
        )
        self._last_key = key
        return True

    def advance(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError("Cache time cannot move backwards")
        self._now += seconds

    def corrupt_latest(self, value: object) -> None:
        if self._last_key is None:
            raise AssertionError("No cached value is available to corrupt")
        entry = self._values[self._last_key]
        self._values[self._last_key] = _CacheEntry(
            value=copy.deepcopy(value),
            expires_at=entry.expires_at,
        )


class QueuedAI:
    def __init__(self, *responses: AIResponse) -> None:
        self._responses = deque(responses)

    async def __call__(
        self,
        task_id: str,
        prompt: str,
        **_: object,
    ) -> ai_helper.LLMResponse:
        del task_id
        if not self._responses:
            raise AssertionError("Unexpected AI dependency call")
        response = self._responses.popleft()
        data = _materialize_response(response.data, prompt)
        return ai_helper.LLMResponse(
            completion=json.dumps(data),
            citation_urls=list(response.citation_urls),
        )


def market_resolver(
    prices: Mapping[str, float | None],
    *,
    currencies: Mapping[str, str] | None = None,
    canonical_tickers: Mapping[str, str] | None = None,
    quote_types: Mapping[str, str] | None = None,
    company_names: Mapping[str, str] | None = None,
    failures: Mapping[str, Exception] | None = None,
) -> Callable[[str], services_stock.ResolvedSymbol]:
    normalized_currencies = currencies or {}
    normalized_tickers = canonical_tickers or {}
    normalized_quote_types = quote_types or {}
    normalized_company_names = company_names or {}
    normalized_failures = failures or {}

    def resolve(ticker: str) -> services_stock.ResolvedSymbol:
        requested = ticker.strip().upper().replace("NYSEARCA:", "NYSE:")
        if requested in normalized_failures:
            raise normalized_failures[requested]
        default_ticker = requested if ":" in requested else f"NASDAQ:{requested}"
        canonical = normalized_tickers.get(requested, default_ticker)
        exchange, symbol = canonical.split(":", 1)
        price = prices.get(requested, prices.get(canonical))
        currency = normalized_currencies.get(
            requested,
            normalized_currencies.get(canonical, "USD"),
        )
        quote_type = normalized_quote_types.get(
            requested,
            normalized_quote_types.get(canonical, "EQUITY"),
        )
        company_name = normalized_company_names.get(
            requested,
            normalized_company_names.get(canonical, f"{symbol} Incorporated"),
        )
        return services_stock.ResolvedSymbol(
            symbol=symbol,
            normalized_symbol=canonical,
            exchange=exchange,
            country="US",
            currency=currency,
            quote_type=quote_type,
            company_name=company_name,
            market_price=price,
        )

    return resolve


def failing_market(ticker: str) -> services_stock.ResolvedSymbol:
    raise AssertionError(f"Unexpected market dependency call for {ticker}")


def _action_reasoning(prompt: str) -> list[dict[str, object]]:
    action_ids = list(dict.fromkeys(re.findall(r'"action_id"\s*:\s*"([^"]+)"', prompt)))
    return [
        {
            "action_id": action_id,
            "priority": priority,
            "reasoning": "This action advances the validated public target.",
        }
        for priority, action_id in enumerate(action_ids, start=1)
    ]


def _portfolio_id(prompt: str) -> str | None:
    json_match = re.search(r'"portfolio_id"\s*:\s*"([^"]+)"', prompt)
    if json_match:
        return json_match.group(1)
    text_match = re.search(r"portfolio_id must be ([A-Za-z0-9_-]+)", prompt)
    return text_match.group(1) if text_match else None


def _materialize_response(value: Any, prompt: str) -> Any:
    if value == PORTFOLIO_ID:
        return _portfolio_id(prompt)
    if value is ACTION_REASONING:
        return _action_reasoning(prompt)
    if isinstance(value, dict):
        return {key: _materialize_response(item, prompt) for key, item in value.items()}
    if isinstance(value, list):
        return [_materialize_response(item, prompt) for item in value]
    return copy.deepcopy(value)
