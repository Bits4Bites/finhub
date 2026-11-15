import asyncio
import json
from unittest import mock

import pytest

from app.services import ai_helper, portfolio_verification
from app.services import msai_spotlight_portfolio as service
from app.services import stock as services_stock
from app.utils import ai_reference
from tests import portfolio_spotlight_fixtures as fixtures

_SOURCE_URL = "https://example.com/issuer-announcement"
_SOURCE_ID = ai_reference.generate_source_id(_SOURCE_URL)


def _resolved_symbol(
    *,
    symbol: str = "AAPL",
    price: float | None = 200,
    currency: str = "USD",
    exchange: str = "NASDAQ",
) -> services_stock.ResolvedSymbol:
    return services_stock.ResolvedSymbol(
        symbol=symbol,
        normalized_symbol=f"{exchange}:{symbol}",
        exchange=exchange,
        country="US",
        currency=currency,
        quote_type="EQUITY",
        company_name=f"{symbol} Incorporated",
        market_price=price,
    )


def _plan_data() -> dict[str, object]:
    return {
        "portfolio_id": "portfolio-id",
        "investor_context_summary": "Growth-focused investor context.",
        "research_priorities": ["Issuer", "Portfolio", "Valuation"],
        "assessment_focus": ["Assess concentration and alignment with the investor context."],
        "investor_constraints": ["Prioritize growth."],
        "data_gaps": [],
    }


def _research_data() -> dict[str, object]:
    return {
        "portfolio_id": "portfolio-id",
        "as_of": "2026-08-21T00:00:00Z",
        "claims": [
            {
                "category": "Issuer",
                "text": "Issuer conditions increased portfolio concentration risk.",
                "affected_tickers": ["NASDAQ:AAPL"],
                "reference_ids": [_SOURCE_URL],
            }
        ],
        "data_gaps": [],
        "references": [
            {
                "id": _SOURCE_URL,
                "title": "Issuer announcement",
                "publisher": "Issuer",
                "source_type": "Issuer",
                "published_at": "2026-08-20",
                "accessed_at": None,
                "url": _SOURCE_URL,
            }
        ],
    }


def _assessment_data(
    *,
    requires_rebalance: bool = True,
    reference_ids: list[str] | None = None,
) -> dict[str, object]:
    risk = fixtures.risk(
        requires_rebalance=requires_rebalance,
        reference_ids=reference_ids if reference_ids is not None else [_SOURCE_ID],
    )
    return {
        "portfolio_id": "portfolio-id",
        "as_of": "2026-08-21T00:00:00Z",
        "overall_data_quality": "High",
        "risks": [risk.model_dump(mode="json")],
        "data_gaps": [],
    }


def _spotlight_responses(
    *,
    citation_urls: list[str] | None = None,
    assessment_data: dict[str, object] | None = None,
) -> list[ai_helper.LLMResponse]:
    return [
        ai_helper.LLMResponse(completion=json.dumps(_plan_data())),
        ai_helper.LLMResponse(
            completion=json.dumps(_research_data()),
            citation_urls=[_SOURCE_URL] if citation_urls is None else citation_urls,
        ),
        ai_helper.LLMResponse(
            completion=json.dumps(assessment_data or _assessment_data()),
        ),
    ]


def test_ai_spotlight_portfolio_filters_zero_positions_and_accepts_fractional_positive_holdings():
    active = fixtures.request_holding(num_shares=1.5)
    zero = fixtures.request_holding("NASDAQ:MSFT", num_shares=0)
    with (
        mock.patch.object(service.cache, "generate_hourly_key", return_value="portfolio-id"),
        mock.patch.object(service.cache, "get", new_callable=mock.AsyncMock, return_value=None),
        mock.patch.object(service.cache, "set", new_callable=mock.AsyncMock, return_value=True) as cache_set,
        mock.patch.object(
            service.portfolio_verification.services_stock,
            "resolve_symbol",
            return_value=_resolved_symbol(),
        ),
        mock.patch.object(
            service.ai_helper,
            "ai_exec_task",
            new_callable=mock.AsyncMock,
            side_effect=_spotlight_responses(),
        ) as ai_exec,
    ):
        result = asyncio.run(
            service.ai_spotlight_portfolio(
                portfolio=[zero, active],
                country="United States",
                investor_theme="  Growth focused  ",
            )
        )

    assert result.portfolio_empty is False
    assert result.snapshot is not None
    assert result.snapshot.country == "US"
    assert result.snapshot.total_market_value == 300
    assert result.snapshot.holdings[0].num_shares == 1.5
    assert result.snapshot.holdings[0].price_source == "MarketData"
    assert result.risks[0].rank == 1
    assert result.risks[0].level == "Critical"
    assert result.rebalance_recommended == "YES"
    assert result.references[0].id == _SOURCE_ID
    assert result.references[0].is_verified is True
    assert [call.args[0] for call in ai_exec.await_args_list] == [
        "SPOTLIGHT_PORTFOLIO_PLAN",
        "SPOTLIGHT_PORTFOLIO_RESEARCH",
        "SPOTLIGHT_PORTFOLIO_ASSESS",
    ]
    assert any(call.kwargs["ttl"] == 60 * 60 for call in cache_set.await_args_list)


def test_ai_spotlight_portfolio_derives_no_rebalance_when_no_action_changes_allocations():
    with (
        mock.patch.object(service.cache, "generate_hourly_key", return_value="portfolio-id"),
        mock.patch.object(service.cache, "get", new_callable=mock.AsyncMock, return_value=None),
        mock.patch.object(service.cache, "set", new_callable=mock.AsyncMock, return_value=True),
        mock.patch.object(
            service.portfolio_verification.services_stock,
            "resolve_symbol",
            return_value=_resolved_symbol(),
        ),
        mock.patch.object(
            service.ai_helper,
            "ai_exec_task",
            new_callable=mock.AsyncMock,
            side_effect=_spotlight_responses(
                assessment_data=_assessment_data(requires_rebalance=False),
            ),
        ),
    ):
        result = asyncio.run(
            service.ai_spotlight_portfolio(
                portfolio=[fixtures.request_holding()],
                country="US",
                investor_theme="Growth focused",
            )
        )

    assert result.rebalance_recommended == "NO"
    assert result.risks[0].requires_rebalance is False


def test_ai_spotlight_portfolio_retains_unverified_sources_with_warning():
    with (
        mock.patch.object(service.cache, "generate_hourly_key", return_value="portfolio-id"),
        mock.patch.object(service.cache, "get", new_callable=mock.AsyncMock, return_value=None),
        mock.patch.object(service.cache, "set", new_callable=mock.AsyncMock, return_value=True),
        mock.patch.object(
            service.portfolio_verification.services_stock,
            "resolve_symbol",
            return_value=_resolved_symbol(),
        ),
        mock.patch.object(
            service.ai_helper,
            "ai_exec_task",
            new_callable=mock.AsyncMock,
            side_effect=_spotlight_responses(citation_urls=[]),
        ),
    ):
        result = asyncio.run(
            service.ai_spotlight_portfolio(
                portfolio=[fixtures.request_holding()],
                country="US",
                investor_theme="Growth focused",
            )
        )

    assert result.references[0].is_verified is False
    assert result.analysis_status == "CompleteWithWarnings"
    assert "could not be provider-verified" in result.validation_warnings[0]


@pytest.mark.parametrize(
    ("portfolio", "country", "theme", "message"),
    [
        ([], "US", "Growth focused", "positive-share position"),
        (
            [fixtures.request_holding(num_shares=0)],
            "US",
            "Growth focused",
            "positive-share position",
        ),
        (
            [fixtures.request_holding()],
            "unknown-market",
            "Growth focused",
            "Unsupported or unknown country",
        ),
        ([fixtures.request_holding()], "US", "   ", "Investor theme must not be empty"),
    ],
)
def test_ai_spotlight_portfolio_rejects_invalid_inputs_before_ai(
    portfolio,
    country,
    theme,
    message,
):
    with (
        mock.patch.object(service.ai_helper, "ai_exec_task", new_callable=mock.AsyncMock) as ai_exec,
        mock.patch.object(
            service.portfolio_verification.services_stock,
            "resolve_symbol",
        ) as resolve_symbol,
        pytest.raises(portfolio_verification.PortfolioInputError, match=message),
    ):
        asyncio.run(
            service.ai_spotlight_portfolio(
                portfolio=portfolio,
                country=country,
                investor_theme=theme,
            )
        )

    ai_exec.assert_not_awaited()
    resolve_symbol.assert_not_called()


def test_ai_spotlight_portfolio_surfaces_market_verification_failure():
    with (
        mock.patch.object(service.cache, "get", new_callable=mock.AsyncMock, return_value=None),
        mock.patch.object(
            service.portfolio_verification.services_stock,
            "resolve_symbol",
            side_effect=OSError("provider unavailable"),
        ),
        mock.patch.object(service.ai_helper, "ai_exec_task", new_callable=mock.AsyncMock) as ai_exec,
        pytest.raises(portfolio_verification.PortfolioVerificationError, match="Unable to verify ticker"),
    ):
        asyncio.run(
            service.ai_spotlight_portfolio(
                portfolio=[fixtures.request_holding()],
                country="US",
                investor_theme="Growth focused",
            )
        )

    ai_exec.assert_not_awaited()


def test_ai_spotlight_portfolio_wraps_exhausted_rate_limit_as_service_error():
    with (
        mock.patch.object(service.cache, "generate_hourly_key", return_value="portfolio-id"),
        mock.patch.object(service.cache, "get", new_callable=mock.AsyncMock, return_value=None),
        mock.patch.object(service.cache, "set", new_callable=mock.AsyncMock, return_value=True),
        mock.patch.object(
            service.portfolio_verification.services_stock,
            "resolve_symbol",
            return_value=_resolved_symbol(),
        ),
        mock.patch.object(
            service.ai_helper,
            "ai_exec_task",
            new_callable=mock.AsyncMock,
            side_effect=ai_helper.LLMRateLimitError("retry budget exhausted"),
        ),
        pytest.raises(service.PortfolioSpotlightAIError, match="planning provider failed"),
    ):
        asyncio.run(
            service.ai_spotlight_portfolio(
                portfolio=[fixtures.request_holding()],
                country="US",
                investor_theme="Growth focused",
            )
        )


def test_ai_spotlight_portfolio_rejects_invalid_structured_ai_result():
    with (
        mock.patch.object(service.cache, "generate_hourly_key", return_value="portfolio-id"),
        mock.patch.object(service.cache, "get", new_callable=mock.AsyncMock, return_value=None),
        mock.patch.object(service.cache, "set", new_callable=mock.AsyncMock, return_value=True),
        mock.patch.object(
            service.portfolio_verification.services_stock,
            "resolve_symbol",
            return_value=_resolved_symbol(),
        ),
        mock.patch.object(
            service.ai_helper,
            "ai_exec_task",
            new_callable=mock.AsyncMock,
            return_value=ai_helper.LLMResponse(completion=json.dumps({"portfolio_id": "wrong"})),
        ),
        pytest.raises(service.PortfolioSpotlightAIError, match="invalid structured data"),
    ):
        asyncio.run(
            service.ai_spotlight_portfolio(
                portfolio=[fixtures.request_holding()],
                country="US",
                investor_theme="Growth focused",
            )
        )


def test_ai_spotlight_portfolio_verifies_market_data_before_returning_final_cache():
    cached = fixtures.analysis()
    with (
        mock.patch.object(
            service.cache,
            "get",
            new_callable=mock.AsyncMock,
            side_effect=[None, cached.model_dump(mode="json")],
        ),
        mock.patch.object(service.cache, "set", new_callable=mock.AsyncMock),
        mock.patch.object(
            service.portfolio_verification.services_stock,
            "resolve_symbol",
            return_value=_resolved_symbol(),
        ) as resolve_symbol,
        mock.patch.object(service.ai_helper, "ai_exec_task", new_callable=mock.AsyncMock) as ai_exec,
    ):
        result = asyncio.run(
            service.ai_spotlight_portfolio(
                portfolio=[fixtures.request_holding()],
                country="US",
                investor_theme="Growth focused",
            )
        )

    assert result == cached
    resolve_symbol.assert_called_once_with("NASDAQ:AAPL")
    ai_exec.assert_not_awaited()


def test_ai_spotlight_portfolio_rejects_invalid_final_cache():
    with (
        mock.patch.object(
            service.cache,
            "get",
            new_callable=mock.AsyncMock,
            side_effect=[None, {"unexpected": "value"}],
        ),
        mock.patch.object(service.cache, "set", new_callable=mock.AsyncMock),
        mock.patch.object(
            service.portfolio_verification.services_stock,
            "resolve_symbol",
            return_value=_resolved_symbol(),
        ),
        pytest.raises(RuntimeError, match="analysis cache contains an invalid value"),
    ):
        asyncio.run(
            service.ai_spotlight_portfolio(
                portfolio=[fixtures.request_holding()],
                country="US",
                investor_theme="Growth focused",
            )
        )
