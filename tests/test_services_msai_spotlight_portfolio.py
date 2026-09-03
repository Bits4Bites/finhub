import asyncio
import json
from collections.abc import Mapping
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import ai_helper
from app.services import msai_spotlight_portfolio as service
from app.services import portfolio_verification as verification
from app.utils import ai_reference as ai_reference_utils
from tests import portfolio_spotlight_fixtures


def _assert_all_object_properties_are_required(value: object) -> None:
    if isinstance(value, Mapping):
        properties = value.get("properties")
        if isinstance(properties, Mapping):
            assert set(value.get("required", [])) == set(properties)
        for nested_value in value.values():
            _assert_all_object_properties_are_required(nested_value)
    elif isinstance(value, list):
        for nested_value in value:
            _assert_all_object_properties_are_required(nested_value)


def _ticker_info(
    *,
    symbol: str = "AAPL",
    price: float | None = 200,
    currency: str = "USD",
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "quoteType": "EQUITY",
        "fullExchangeName": "NasdaqGS",
        "currency": currency,
        "regularMarketPrice": price,
        "longName": "Apple Inc.",
    }


def _ticker(info: dict[str, object]) -> MagicMock:
    ticker = MagicMock()
    ticker.info = info
    return ticker


def _research_response_data(portfolio_id: str = "portfolio-id") -> dict[str, object]:
    source_url = "https://example.com/issuer-announcement"
    return {
        "portfolio_id": portfolio_id,
        "as_of": "2026-08-21T00:00:00Z",
        "claims": [
            {
                "category": "Issuer",
                "text": "Issuer conditions increased portfolio risk.",
                "affected_tickers": ["NASDAQ:AAPL"],
                "reference_ids": [source_url],
            }
        ],
        "data_gaps": [],
        "references": [
            {
                "id": source_url,
                "title": "Issuer announcement",
                "publisher": "Issuer",
                "source_type": "Issuer",
                "published_at": "2026-08-20",
                "accessed_at": None,
                "url": source_url,
            }
        ],
    }


def _plan_response_data(portfolio_id: str = "portfolio-id") -> dict[str, object]:
    return {
        "portfolio_id": portfolio_id,
        "investor_context_summary": "Growth-focused investor context.",
        "research_priorities": ["Issuer", "Portfolio", "Valuation"],
        "assessment_focus": ["Assess concentration and alignment with the available investor context."],
        "investor_constraints": ["Prioritize growth."],
        "data_gaps": [],
    }


def _assessment_response_data(portfolio_id: str = "portfolio-id") -> dict[str, object]:
    return {
        "portfolio_id": portfolio_id,
        "as_of": "2026-08-21T00:00:00Z",
        "overall_data_quality": "High",
        "risks": [portfolio_spotlight_fixtures.risk().model_dump(mode="json")],
        "data_gaps": [],
    }


def test_empty_portfolio_is_rejected_before_verification_and_ai():
    with (
        patch.object(
            service.portfolio_verification,
            "verify_portfolio",
            new_callable=AsyncMock,
        ) as mock_verify,
        patch.object(service.ai_helper, "ai_exec_task", new_callable=AsyncMock) as mock_ai_exec,
        pytest.raises(verification.PortfolioInputError, match="positive-share position"),
    ):
        asyncio.run(
            service.ai_spotlight_portfolio(
                portfolio=[],
                country="AU",
                investor_theme="Growth focused",
            )
        )

    mock_verify.assert_not_awaited()
    mock_ai_exec.assert_not_awaited()


def test_zero_share_positions_are_rejected_before_verification_and_ai():
    with (
        patch.object(
            service.portfolio_verification,
            "verify_portfolio",
            new_callable=AsyncMock,
        ) as mock_verify,
        patch.object(service.ai_helper, "ai_exec_task", new_callable=AsyncMock) as mock_ai_exec,
        pytest.raises(verification.PortfolioInputError, match="positive-share position"),
    ):
        asyncio.run(
            service.ai_spotlight_portfolio(
                portfolio=[portfolio_spotlight_fixtures.request_holding(num_shares=0)],
                country="US",
                investor_theme="Growth focused",
            )
        )

    mock_verify.assert_not_awaited()
    mock_ai_exec.assert_not_awaited()


@pytest.mark.parametrize("investor_theme", ["", "   "])
def test_blank_investor_theme_is_rejected_before_verification(investor_theme):
    with (
        patch.object(
            service.portfolio_verification,
            "verify_portfolio",
            new_callable=AsyncMock,
        ) as mock_verify,
        pytest.raises(verification.PortfolioInputError, match="Investor theme must not be empty"),
    ):
        asyncio.run(
            service.ai_spotlight_portfolio(
                portfolio=[portfolio_spotlight_fixtures.request_holding()],
                country="US",
                investor_theme=investor_theme,
            )
        )

    mock_verify.assert_not_awaited()


def test_verification_uses_current_market_data_and_calculates_snapshot():
    with (
        patch.object(verification.cache, "get", new_callable=AsyncMock, return_value=None),
        patch.object(
            verification.cache,
            "set",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_cache_set,
        patch.object(verification.yf, "Ticker", return_value=_ticker(_ticker_info())),
    ):
        snapshot = asyncio.run(
            verification.verify_portfolio(
                [portfolio_spotlight_fixtures.request_holding()],
                country="US",
            )
        )

    holding = snapshot.holdings[0]
    assert holding.ticker == "NASDAQ:AAPL"
    assert holding.market_price == 200
    assert holding.price_source == "MarketData"
    assert holding.market_value == 2000
    assert holding.current_allocation == 1
    assert holding.allocation_drift == pytest.approx(0.4)
    assert holding.unrealized_profit_loss == 500
    mock_cache_set.assert_awaited_once()
    assert mock_cache_set.await_args.kwargs["ttl"] == 5 * 60


def test_verification_uses_client_price_only_as_fallback():
    info = _ticker_info(price=None)
    with (
        patch.object(verification.cache, "get", new_callable=AsyncMock, return_value=None),
        patch.object(verification.cache, "set", new_callable=AsyncMock, return_value=True),
        patch.object(verification.yf, "Ticker", return_value=_ticker(info)),
    ):
        snapshot = asyncio.run(
            verification.verify_portfolio(
                [portfolio_spotlight_fixtures.request_holding()],
                country="US",
            )
        )

    assert snapshot.holdings[0].price_source == "Client"
    assert "client-supplied market price" in snapshot.data_gaps[0]


def test_verification_rejects_duplicate_canonical_tickers():
    positions = [
        portfolio_spotlight_fixtures.request_holding("AAPL"),
        portfolio_spotlight_fixtures.request_holding("NASDAQ:AAPL"),
    ]
    with (
        patch.object(verification.cache, "get", new_callable=AsyncMock, return_value=None),
        patch.object(verification.yf, "Ticker", return_value=_ticker(_ticker_info())),
        pytest.raises(verification.PortfolioInputError, match="Duplicate"),
    ):
        asyncio.run(verification.verify_portfolio(positions, country="US"))


def test_verification_rejects_mixed_currency_portfolio():
    positions = [
        portfolio_spotlight_fixtures.request_holding("NASDAQ:AAPL"),
        portfolio_spotlight_fixtures.request_holding("NASDAQ:MSFT"),
    ]
    tickers = [
        _ticker(_ticker_info(symbol="AAPL", currency="USD")),
        _ticker(_ticker_info(symbol="MSFT", currency="AUD")),
    ]
    with (
        patch.object(verification.cache, "get", new_callable=AsyncMock, return_value=None),
        patch.object(verification.yf, "Ticker", side_effect=tickers),
        pytest.raises(verification.PortfolioInputError, match="Mixed-currency"),
    ):
        asyncio.run(verification.verify_portfolio(positions, country="US"))


def test_planning_uses_required_theme_and_structured_output():
    llm_response = ai_helper.LLMResponse(completion=json.dumps(_plan_response_data()))
    with (
        patch.object(service.cache, "get", new_callable=AsyncMock, return_value=None),
        patch.object(service.cache, "set", new_callable=AsyncMock, return_value=True) as mock_cache_set,
        patch.object(
            service.ai_helper,
            "ai_exec_task",
            new_callable=AsyncMock,
            return_value=llm_response,
        ) as mock_ai_exec,
    ):
        plan = asyncio.run(
            service._build_analysis_plan(
                "portfolio-id",
                portfolio_spotlight_fixtures.snapshot(),
                investor_theme="Growth focused",
            )
        )

    assert plan.investor_context_summary == "Growth-focused investor context."
    assert (
        "BEGIN_VALIDATED_UNTRUSTED_INVESTOR_THEME\nGrowth focused\nEND_VALIDATED_UNTRUSTED_INVESTOR_THEME"
    ) in mock_ai_exec.await_args.args[1]
    assert mock_ai_exec.await_args.args[0] == "SPOTLIGHT_PORTFOLIO_PLAN"
    assert mock_ai_exec.await_args.kwargs["schema_name"] == "portfolio_spotlight_plan"
    assert mock_ai_exec.await_args.kwargs["response_json_schema"] == service._PortfolioAnalysisPlan.model_json_schema()
    mock_cache_set.assert_awaited_once()
    assert mock_cache_set.await_args.kwargs["ttl"] == 60 * 60


def test_planning_reuses_cached_validated_stage():
    expected = portfolio_spotlight_fixtures.plan()
    with (
        patch.object(
            service.cache,
            "get",
            new_callable=AsyncMock,
            return_value=expected.model_dump(mode="json"),
        ),
        patch.object(service.cache, "set", new_callable=AsyncMock) as mock_cache_set,
        patch.object(service.ai_helper, "ai_exec_task", new_callable=AsyncMock) as mock_ai_exec,
    ):
        plan = asyncio.run(
            service._build_analysis_plan(
                "portfolio-id",
                portfolio_spotlight_fixtures.snapshot(),
                investor_theme="Growth focused",
            )
        )

    assert plan == expected
    mock_ai_exec.assert_not_awaited()
    mock_cache_set.assert_not_awaited()


@pytest.mark.parametrize(
    "response_updates",
    [
        {"portfolio_id": "different-portfolio"},
        {"investor_context_summary": None},
        {"investor_constraints": ["Prioritize growth.", "Prioritize growth."]},
    ],
)
def test_planning_rejects_inconsistent_structured_output(response_updates):
    response_data = _plan_response_data()
    response_data.update(response_updates)
    with (
        patch.object(service.cache, "get", new_callable=AsyncMock, return_value=None),
        patch.object(service.cache, "set", new_callable=AsyncMock) as mock_cache_set,
        patch.object(
            service.ai_helper,
            "ai_exec_task",
            new_callable=AsyncMock,
            return_value=ai_helper.LLMResponse(completion=json.dumps(response_data)),
        ),
        pytest.raises(
            service.PortfolioSpotlightAIError,
            match="invalid structured data",
        ),
    ):
        asyncio.run(
            service._build_analysis_plan(
                "portfolio-id",
                portfolio_spotlight_fixtures.snapshot(),
                investor_theme="Growth focused",
            )
        )

    mock_cache_set.assert_not_awaited()


def test_research_uses_structured_output_and_verified_sources():
    source_url = "https://example.com/issuer-announcement"
    llm_response = ai_helper.LLMResponse(
        completion=json.dumps(_research_response_data()),
        citation_urls=[source_url],
    )
    with (
        patch.object(service.cache, "get", new_callable=AsyncMock, return_value=None),
        patch.object(service.cache, "set", new_callable=AsyncMock, return_value=True) as mock_cache_set,
        patch.object(
            service.ai_helper,
            "ai_exec_task",
            new_callable=AsyncMock,
            return_value=llm_response,
        ) as mock_ai_exec,
    ):
        research = asyncio.run(
            service._research_portfolio(
                "portfolio-id",
                portfolio_spotlight_fixtures.snapshot(),
                portfolio_spotlight_fixtures.plan(),
                investor_theme="Growth focused",
            )
        )

    expected_id = ai_reference_utils.generate_source_id(source_url)
    assert research.references[0].id == expected_id
    assert research.references[0].is_verified is True
    assert mock_ai_exec.await_args.args[0] == "SPOTLIGHT_PORTFOLIO_RESEARCH"
    assert mock_ai_exec.await_args.kwargs["schema_name"] == "portfolio_spotlight_research"
    assert mock_ai_exec.await_args.kwargs["response_json_schema"] == (
        service._PortfolioResearchDraft.model_json_schema()
    )
    mock_cache_set.assert_awaited_once()
    assert mock_cache_set.await_args.kwargs["ttl"] == 60 * 60


def test_research_reuses_cached_validated_stage():
    expected = portfolio_spotlight_fixtures.research()
    with (
        patch.object(
            service.cache,
            "get",
            new_callable=AsyncMock,
            return_value=expected.model_dump(mode="json"),
        ),
        patch.object(service.cache, "set", new_callable=AsyncMock) as mock_cache_set,
        patch.object(service.ai_helper, "ai_exec_task", new_callable=AsyncMock) as mock_ai_exec,
    ):
        research = asyncio.run(
            service._research_portfolio(
                "portfolio-id",
                portfolio_spotlight_fixtures.snapshot(),
                portfolio_spotlight_fixtures.plan(),
                investor_theme="Growth focused",
            )
        )

    assert research == expected
    mock_ai_exec.assert_not_awaited()
    mock_cache_set.assert_not_awaited()


def test_assessment_uses_structured_output_without_new_research():
    llm_response = ai_helper.LLMResponse(
        completion=json.dumps(_assessment_response_data()),
    )
    with (
        patch.object(service.cache, "get", new_callable=AsyncMock, return_value=None),
        patch.object(service.cache, "set", new_callable=AsyncMock, return_value=True) as mock_cache_set,
        patch.object(
            service.ai_helper,
            "ai_exec_task",
            new_callable=AsyncMock,
            return_value=llm_response,
        ) as mock_ai_exec,
    ):
        assessment = asyncio.run(
            service._assess_portfolio(
                "portfolio-id",
                portfolio_spotlight_fixtures.snapshot(),
                portfolio_spotlight_fixtures.research(),
                portfolio_spotlight_fixtures.plan(),
                investor_theme="Growth focused",
            )
        )

    assert assessment.risks[0].level == "Critical"
    assert mock_ai_exec.await_args.args[0] == "SPOTLIGHT_PORTFOLIO_ASSESS"
    assert mock_ai_exec.await_args.kwargs["schema_name"] == "portfolio_spotlight_assessment"
    assert mock_ai_exec.await_args.kwargs["response_json_schema"] == (
        service._PortfolioAssessmentDraft.model_json_schema()
    )
    mock_cache_set.assert_awaited_once()
    assert mock_cache_set.await_args.kwargs["ttl"] == 60 * 60


def test_assessment_rejects_unknown_reference_ids():
    response_data = _assessment_response_data()
    response_data["risks"][0]["reference_ids"] = ["unknown-source"]
    with (
        patch.object(service.cache, "get", new_callable=AsyncMock, return_value=None),
        patch.object(
            service.ai_helper,
            "ai_exec_task",
            new_callable=AsyncMock,
            return_value=ai_helper.LLMResponse(completion=json.dumps(response_data)),
        ),
        pytest.raises(service.PortfolioSpotlightAIError, match="invalid structured data"),
    ):
        asyncio.run(
            service._assess_portfolio(
                "portfolio-id",
                portfolio_spotlight_fixtures.snapshot(),
                portfolio_spotlight_fixtures.research(),
                portfolio_spotlight_fixtures.plan(),
                investor_theme="Growth focused",
            )
        )


def test_final_analysis_derives_yes_no_rebalance_flag():
    plan = portfolio_spotlight_fixtures.plan().model_copy(
        update={"data_gaps": ["Investor liquidity needs were not supplied."]}
    )
    analysis = service._build_analysis(
        portfolio_spotlight_fixtures.snapshot(),
        plan,
        portfolio_spotlight_fixtures.research(),
        portfolio_spotlight_fixtures.assessment(),
    )

    assert analysis.rebalance_recommended == "YES"
    assert analysis.risks[0].requires_rebalance is True
    assert "Investor liquidity needs were not supplied." in analysis.data_gaps


def test_full_flow_reuses_final_analysis_cache_after_verification():
    cached = portfolio_spotlight_fixtures.analysis()
    with (
        patch.object(
            service.portfolio_verification,
            "verify_portfolio",
            new_callable=AsyncMock,
            return_value=portfolio_spotlight_fixtures.verified_portfolio(),
        ),
        patch.object(
            service.cache,
            "get",
            new_callable=AsyncMock,
            return_value=cached.model_dump(mode="json"),
        ),
        patch.object(service, "_research_portfolio", new_callable=AsyncMock) as mock_research,
        patch.object(service, "_assess_portfolio", new_callable=AsyncMock) as mock_assess,
        patch.object(service, "_build_analysis_plan", new_callable=AsyncMock) as mock_plan,
    ):
        result = asyncio.run(
            service.ai_spotlight_portfolio(
                portfolio=[portfolio_spotlight_fixtures.request_holding()],
                country="US",
                investor_theme="Growth focused",
            )
        )

    assert result == cached
    mock_plan.assert_not_awaited()
    mock_research.assert_not_awaited()
    mock_assess.assert_not_awaited()


def test_full_flow_normalizes_theme_before_ai_stages():
    plan = portfolio_spotlight_fixtures.plan()
    research = portfolio_spotlight_fixtures.research()
    assessment = portfolio_spotlight_fixtures.assessment()
    with (
        patch.object(
            service.portfolio_verification,
            "verify_portfolio",
            new_callable=AsyncMock,
            return_value=portfolio_spotlight_fixtures.verified_portfolio(),
        ) as mock_verify,
        patch.object(service.cache, "get", new_callable=AsyncMock, return_value=None),
        patch.object(service.cache, "set", new_callable=AsyncMock, return_value=True),
        patch.object(
            service,
            "_build_analysis_plan",
            new_callable=AsyncMock,
            return_value=plan,
        ) as mock_plan,
        patch.object(
            service,
            "_research_portfolio",
            new_callable=AsyncMock,
            return_value=research,
        ) as mock_research,
        patch.object(
            service,
            "_assess_portfolio",
            new_callable=AsyncMock,
            return_value=assessment,
        ) as mock_assess,
    ):
        stages = MagicMock()
        stages.attach_mock(mock_verify, "verify")
        stages.attach_mock(mock_plan, "plan")
        stages.attach_mock(mock_research, "research")
        stages.attach_mock(mock_assess, "assess")
        result = asyncio.run(
            service.ai_spotlight_portfolio(
                portfolio=[portfolio_spotlight_fixtures.request_holding()],
                country="US",
                investor_theme="  Growth focused  ",
            )
        )

    assert result.portfolio_empty is False
    assert [stage[0] for stage in stages.mock_calls] == [
        "verify",
        "plan",
        "research",
        "assess",
    ]
    assert mock_plan.await_args.kwargs["investor_theme"] == "Growth focused"
    assert mock_research.await_args.kwargs["investor_theme"] == "Growth focused"
    assert mock_research.await_args.args[2] == plan
    assert mock_assess.await_args.kwargs["investor_theme"] == "Growth focused"
    assert mock_assess.await_args.args[3] == plan


@pytest.mark.parametrize(
    "response_model",
    [
        service._PortfolioAnalysisPlan,
        service._PortfolioResearchDraft,
        service._PortfolioAssessmentDraft,
    ],
)
def test_provider_schema_requires_every_declared_property(response_model):
    schema = ai_helper._openai_compatible_json_schema(response_model.model_json_schema())

    _assert_all_object_properties_are_required(schema)


def test_task_configuration_uses_terra_medium_for_planning():
    plan = service.config.settings_llm_task.tasks["SPOTLIGHT_PORTFOLIO_PLAN"]
    research = service.config.settings_llm_task.tasks["SPOTLIGHT_PORTFOLIO_RESEARCH"]
    assessment = service.config.settings_llm_task.tasks["SPOTLIGHT_PORTFOLIO_ASSESS"]

    assert plan.model == "gpt-5.6-terra"
    assert plan.reasoning_effort == "Medium"
    assert plan.use_web_search is False
    assert research.model == "gpt-5.6-terra"
    assert research.reasoning_effort == "High"
    assert research.use_web_search is True
    assert research.max_tool_calls == 0
    assert assessment.model == "gpt-5.6-terra"
    assert assessment.reasoning_effort == "High"
    assert assessment.use_web_search is False
