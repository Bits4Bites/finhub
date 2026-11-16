import asyncio
from unittest import mock

import pytest

from app.services import ai_helper, portfolio_verification
from app.services import msai_spotlight_portfolio as service
from app.utils import ai_reference
from tests import portfolio_service_fixtures as boundaries
from tests import portfolio_spotlight_fixtures as fixtures

_SOURCE_URL = "https://example.com/issuer-announcement"
_SOURCE_ID = ai_reference.generate_source_id(_SOURCE_URL)


def _plan_data() -> dict[str, object]:
    return {
        "portfolio_id": boundaries.PORTFOLIO_ID,
        "investor_context_summary": "Growth-focused investor context.",
        "research_priorities": ["Issuer", "Portfolio", "Valuation"],
        "assessment_focus": ["Assess concentration and alignment with the investor context."],
        "investor_constraints": ["Prioritize growth."],
        "data_gaps": [],
    }


def _research_data() -> dict[str, object]:
    return {
        "portfolio_id": boundaries.PORTFOLIO_ID,
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


def _assessment_data(risks) -> dict[str, object]:
    return {
        "portfolio_id": boundaries.PORTFOLIO_ID,
        "as_of": "2026-08-21T00:00:00Z",
        "overall_data_quality": "High",
        "risks": [risk.model_dump(mode="json") for risk in risks],
        "data_gaps": [],
    }


def _risk(**kwargs):
    return fixtures.risk(reference_ids=[_SOURCE_ID], **kwargs)


def _spotlight_ai(
    *,
    risks,
    citation_urls: tuple[str, ...] = (_SOURCE_URL,),
) -> boundaries.QueuedAI:
    return boundaries.QueuedAI(
        boundaries.AIResponse(_plan_data()),
        boundaries.AIResponse(
            _research_data(),
            citation_urls=citation_urls,
        ),
        boundaries.AIResponse(_assessment_data(risks)),
    )


def _invoke_spotlight(
    portfolio,
    *,
    country: str,
    investor_theme: str,
    ai,
    cache: boundaries.MemoryCache | None = None,
    market=None,
):
    memory_cache = cache or boundaries.MemoryCache()
    resolver = market or boundaries.market_resolver({"NASDAQ:AAPL": 200, "NASDAQ:MSFT": 300})
    with (
        mock.patch.object(service.cache, "get", new=memory_cache.get),
        mock.patch.object(service.cache, "set", new=memory_cache.set),
        mock.patch.object(service.ai_helper, "ai_exec_task", new=ai),
        mock.patch.object(
            service.portfolio_verification.services_stock,
            "resolve_symbol",
            new=resolver,
        ),
    ):
        return asyncio.run(
            service.ai_spotlight_portfolio(
                portfolio=portfolio,
                country=country,
                investor_theme=investor_theme,
            )
        )


def test_ai_spotlight_portfolio_filters_zero_positions_and_returns_ordered_risks():
    risks = [
        _risk(rank=1, level="Critical", requires_rebalance=True),
        _risk(rank=2, level="High", requires_rebalance=False),
        _risk(rank=3, level="Medium", requires_rebalance=False),
    ]
    result = _invoke_spotlight(
        [
            fixtures.request_holding("NASDAQ:MSFT", num_shares=0),
            fixtures.request_holding(num_shares=1.5),
        ],
        country="United States",
        investor_theme="  Growth focused  ",
        ai=_spotlight_ai(risks=risks),
    )

    assert result.portfolio_empty is False
    assert result.snapshot is not None
    assert result.snapshot.country == "US"
    assert result.snapshot.total_market_value == 300
    assert [holding.ticker for holding in result.snapshot.holdings] == ["NASDAQ:AAPL"]
    assert result.snapshot.holdings[0].num_shares == 1.5
    assert [risk.rank for risk in result.risks] == [1, 2, 3]
    assert [risk.level for risk in result.risks] == ["Critical", "High", "Medium"]
    assert result.rebalance_recommended == "YES"
    assert result.references[0].id == _SOURCE_ID
    assert result.references[0].is_verified is True


def test_ai_spotlight_portfolio_returns_no_risks_without_rebalance_or_sources():
    result = _invoke_spotlight(
        [fixtures.request_holding()],
        country="US",
        investor_theme="Growth focused",
        ai=_spotlight_ai(risks=[]),
    )

    assert result.risks == []
    assert result.rebalance_recommended == "NO"
    assert result.references == []
    assert result.analysis_status == "Complete"


def test_ai_spotlight_portfolio_retains_unmatched_structural_sources_as_unverified():
    result = _invoke_spotlight(
        [fixtures.request_holding()],
        country="US",
        investor_theme="Growth focused",
        ai=_spotlight_ai(
            risks=[_risk()],
            citation_urls=(),
        ),
    )

    assert result.references
    assert result.references[0].is_verified is False
    assert result.analysis_status == "CompleteWithWarnings"
    assert result.validation_warnings


def test_ai_spotlight_portfolio_rejects_out_of_order_risks():
    risks = [
        _risk(rank=1, level="High"),
        _risk(rank=2, level="Critical"),
    ]

    with pytest.raises(service.PortfolioSpotlightAIError):
        _invoke_spotlight(
            [fixtures.request_holding()],
            country="US",
            investor_theme="Growth focused",
            ai=_spotlight_ai(risks=risks),
        )


@pytest.mark.parametrize(
    ("portfolio", "country", "theme"),
    [
        ([], "US", "Growth focused"),
        ([fixtures.request_holding(num_shares=0)], "US", "Growth focused"),
        ([fixtures.request_holding()], "unknown-market", "Growth focused"),
        ([fixtures.request_holding()], "US", "   "),
    ],
)
def test_ai_spotlight_portfolio_rejects_invalid_inputs(portfolio, country, theme):
    with pytest.raises(portfolio_verification.PortfolioInputError):
        _invoke_spotlight(
            portfolio,
            country=country,
            investor_theme=theme,
            ai=boundaries.QueuedAI(),
        )


def test_ai_spotlight_portfolio_surfaces_market_verification_failure():
    market = boundaries.market_resolver(
        {"NASDAQ:AAPL": 200},
        failures={"NASDAQ:AAPL": OSError("provider unavailable")},
    )

    with pytest.raises(portfolio_verification.PortfolioVerificationError):
        _invoke_spotlight(
            [fixtures.request_holding()],
            country="US",
            investor_theme="Growth focused",
            ai=boundaries.QueuedAI(),
            market=market,
        )


def test_ai_spotlight_portfolio_reports_ai_provider_failure():
    async def rate_limited(*args, **kwargs):
        del args, kwargs
        raise ai_helper.LLMRateLimitError("retry budget exhausted")

    with pytest.raises(service.PortfolioSpotlightAIError):
        _invoke_spotlight(
            [fixtures.request_holding()],
            country="US",
            investor_theme="Growth focused",
            ai=rate_limited,
        )


def test_ai_spotlight_portfolio_rejects_invalid_structured_ai_output():
    with pytest.raises(service.PortfolioSpotlightAIError):
        _invoke_spotlight(
            [fixtures.request_holding()],
            country="US",
            investor_theme="Growth focused",
            ai=boundaries.QueuedAI(boundaries.AIResponse({"unexpected": "response"})),
        )


def test_ai_spotlight_portfolio_repeated_calls_return_equal_public_results():
    cache = boundaries.MemoryCache()
    first = _invoke_spotlight(
        [fixtures.request_holding()],
        country="US",
        investor_theme="Growth focused",
        ai=_spotlight_ai(risks=[_risk()]),
        cache=cache,
    )
    second = _invoke_spotlight(
        [fixtures.request_holding()],
        country="US",
        investor_theme="Growth focused",
        ai=boundaries.QueuedAI(),
        cache=cache,
        market=boundaries.failing_market,
    )

    assert second == first


def test_ai_spotlight_portfolio_rejects_an_opaque_invalid_cached_result():
    cache = boundaries.MemoryCache()
    _invoke_spotlight(
        [fixtures.request_holding()],
        country="US",
        investor_theme="Growth focused",
        ai=_spotlight_ai(risks=[_risk()]),
        cache=cache,
    )
    cache.corrupt_latest({"invalid": "cached spotlight"})

    with pytest.raises(RuntimeError):
        _invoke_spotlight(
            [fixtures.request_holding()],
            country="US",
            investor_theme="Growth focused",
            ai=boundaries.QueuedAI(),
            cache=cache,
            market=boundaries.failing_market,
        )


def test_ai_spotlight_portfolio_verifies_market_changes_before_reusing_analysis():
    cache = boundaries.MemoryCache()
    first = _invoke_spotlight(
        [fixtures.request_holding()],
        country="US",
        investor_theme="Growth focused",
        ai=_spotlight_ai(risks=[_risk()]),
        cache=cache,
    )
    cache.advance(301)
    second = _invoke_spotlight(
        [fixtures.request_holding()],
        country="US",
        investor_theme="Growth focused",
        ai=_spotlight_ai(risks=[_risk()]),
        cache=cache,
        market=boundaries.market_resolver({"NASDAQ:AAPL": 250}),
    )

    assert first.snapshot is not None
    assert second.snapshot is not None
    assert first.snapshot.total_market_value == 2_000
    assert second.snapshot.total_market_value == 2_500
    assert second != first


def test_ai_spotlight_portfolio_refreshes_public_analysis_after_cache_expiry():
    cache = boundaries.MemoryCache()
    first = _invoke_spotlight(
        [fixtures.request_holding()],
        country="US",
        investor_theme="Growth focused",
        ai=_spotlight_ai(risks=[_risk()]),
        cache=cache,
    )
    cache.advance(3601)
    second = _invoke_spotlight(
        [fixtures.request_holding()],
        country="US",
        investor_theme="Growth focused",
        ai=_spotlight_ai(risks=[]),
        cache=cache,
    )

    assert first.risks
    assert second.risks == []
    assert second.rebalance_recommended == "NO"
