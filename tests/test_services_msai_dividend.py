import asyncio
from collections.abc import Mapping
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from app.models import events_dividends as models_dividends
from app.services import ai_helper
from app.services import msai_analyze_div_event as service
from tests import dividend_fixtures


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


def _history() -> pd.DataFrame:
    dates = pd.date_range("2025-01-01", periods=12, freq="D", tz="Australia/Sydney")
    history = pd.DataFrame(
        {
            "Open": np.full(12, 100.0),
            "High": np.full(12, 101.0),
            "Low": np.full(12, 99.0),
            "Close": np.full(12, 100.0),
            "Volume": np.full(12, 1_000.0),
            "Dividends": np.zeros(12),
        },
        index=dates,
    )
    history.iloc[2, history.columns.get_loc("Open")] = 98.0
    history.iloc[2, history.columns.get_loc("Close")] = 97.0
    history.iloc[2, history.columns.get_loc("Low")] = 96.0
    history.iloc[2, history.columns.get_loc("Dividends")] = 2.0
    history.iloc[3, history.columns.get_loc("Close")] = 98.0
    history.iloc[3, history.columns.get_loc("Low")] = 95.0
    history.iloc[4, history.columns.get_loc("Close")] = 100.0
    history.iloc[4, history.columns.get_loc("Low")] = 97.0
    history.iloc[5, history.columns.get_loc("Close")] = 90.0
    history.iloc[5, history.columns.get_loc("Low")] = 89.0
    return history


def _private_research() -> service._DividendResearch:
    section = service._DividendResearchSection.model_validate(dividend_fixtures.evidence_section().model_dump())
    return service._DividendResearch(
        symbol="CBA.AX",
        as_of=datetime(2026, 5, 28, tzinfo=UTC),
        dividend_terms=section,
        issuer_outlook=section,
        event_risks=section,
        market_context=section,
        references=[dividend_fixtures.reference()],
    )


def _assessment() -> service._DividendAssessmentDraft:
    return service._DividendAssessmentDraft(
        symbol="CBA.AX",
        as_of=datetime(2026, 5, 28, tzinfo=UTC),
        overall_data_quality="High",
        evidence_adjusted_ex_date_close_drop=dividend_fixtures.drop_estimate(),
        evidence_adjusted_pre_ex_close_recovery=dividend_fixtures.recovery_estimate(
            dividend_fixtures.numeric_range(100.0)
        ),
        evidence_adjusted_capture_break_even_recovery=dividend_fixtures.recovery_estimate(
            dividend_fixtures.numeric_range(98.0)
        ),
        evidence_adjusted_discount_break_even_recovery=dividend_fixtures.recovery_estimate(
            dividend_fixtures.numeric_range(98.0),
            probability=0.55,
        ),
        dividend_capture=dividend_fixtures.strategy("DividendCapture").model_dump(),
        post_dividend_discount=dividend_fixtures.strategy(
            "PostDividendDiscount",
            probability=0.55,
        ).model_dump(),
        comparison_rationale="Dividend capture has a material probability advantage.",
        comparison_reference_ids=[dividend_fixtures.SOURCE_ID],
    )


def _assessment_result() -> service._DividendAssessmentResult:
    return service._DividendAssessmentResult(
        assessment=_assessment(),
        validation_warnings=(),
    )


def test_extracts_distinct_drop_and_recovery_metrics():
    samples = service._extract_dividend_samples(
        _history(),
        sample_cutoff=datetime(2025, 1, 12).date(),
        holding_period_days=7,
        costs=models_dividends.DividendTransactionCosts(),
    )

    assert len(samples) == 1
    sample = samples[0]
    assert sample.open_drop_ratio == 1.0
    assert sample.close_drop_ratio == 1.5
    assert sample.intraday_low_drop_ratio == 2.0
    assert sample.drawdown_ratio == 2.5
    assert sample.pre_ex_close_recovery_days == 2
    assert sample.capture_break_even_recovery_days == 1
    assert sample.discount_break_even_recovery_days == 0


def test_recovery_uses_candidate_day_volume():
    history = _history()
    history.iloc[4, history.columns.get_loc("Volume")] = 0.0
    history.iloc[5, history.columns.get_loc("Close")] = 100.0

    recovery_days = service._first_recovery_days(
        history.iloc[2:7],
        history.index[2],
        100.0,
    )

    assert recovery_days == 3


def test_drop_estimate_caps_loss_at_reference_price():
    sample = service._DividendSample(
        open_drop_ratio=10.0,
        close_drop_ratio=10.0,
        intraday_low_drop_ratio=10.0,
        drawdown_ratio=10.0,
        pre_ex_close_recovery_days=None,
        capture_break_even_recovery_days=None,
        discount_break_even_recovery_days=None,
    )
    context = dividend_fixtures.event_context().model_copy(update={"reference_price": 10.0, "dividend_amount": 2.0})

    estimate = service._drop_estimate([sample], "close_drop_ratio", context)

    assert estimate.drop_amount.maximum == 10.0
    assert estimate.drop_percent.maximum == 1.0
    assert estimate.drop_to_dividend_ratio.maximum == 5.0
    assert estimate.estimated_price.minimum == 0.0


def test_normalize_history_removes_proven_incomplete_session():
    timezone = ZoneInfo("Australia/Sydney")
    today = datetime.now(timezone).date()
    dates = pd.date_range(end=today, periods=91, freq="D", tz=timezone)
    history = pd.DataFrame(
        {
            "Open": np.full(91, 100.0),
            "High": np.full(91, 101.0),
            "Low": np.full(91, 99.0),
            "Close": np.full(91, 100.0),
            "Volume": np.full(91, 1_000.0),
            "Dividends": np.zeros(91),
        },
        index=dates,
    )

    normalized = service._normalize_history(history, timezone, market_state="REGULAR")

    assert len(normalized) == 90
    assert normalized.index[-1].date() < today


def test_resolves_timezone_from_market_history_without_geographic_default():
    assert service._resolve_exchange_timezone({}, _history()) == ZoneInfo("Australia/Sydney")


def test_rejects_missing_exchange_timezone():
    with pytest.raises(service.DividendEventInsufficientDataError, match="exchange timezone"):
        service._resolve_exchange_timezone({}, pd.DataFrame())


def test_prompt_rendering_does_not_reprocess_untrusted_placeholders():
    with patch.object(
        service.ai_prompt_utils,
        "load_prompt",
        return_value="{{FIRST}} / {{SECOND}}",
    ):
        prompt = service._render_prompt(
            "unused.txt",
            {
                "FIRST": "{{SECOND}}",
                "SECOND": "trusted",
            },
        )

    assert prompt == "{{SECOND}} / trusted"


def test_repair_and_finalize_research_prunes_orphans_and_marks_unverified():
    source_url = "https://example.com/dividend"
    section = {
        "facts": [
            {"text": "Supported fact.", "reference_ids": [source_url]},
            {"text": "Unsupported fact.", "reference_ids": ["https://missing.example/fact"]},
        ],
        "data_gaps": [],
        "reference_ids": [source_url, "https://missing.example/section"],
    }
    raw = service._DividendResearchResponse.model_validate(
        {
            "symbol": "CBA.AX",
            "as_of": datetime(2026, 5, 28, tzinfo=UTC),
            "dividend_terms": section,
            "issuer_outlook": {
                "facts": [{"text": "Outlook fact.", "reference_ids": [source_url]}],
                "data_gaps": [],
                "reference_ids": [source_url],
            },
            "event_risks": {
                "facts": [{"text": "Risk fact.", "reference_ids": [source_url]}],
                "data_gaps": [],
                "reference_ids": [source_url],
            },
            "market_context": {
                "facts": [{"text": "Market fact.", "reference_ids": [source_url]}],
                "data_gaps": [],
                "reference_ids": [source_url],
            },
            "references": [
                {
                    "id": source_url,
                    "title": "Dividend announcement",
                    "publisher": "ASX",
                    "source_type": "Exchange",
                    "published_at": None,
                    "accessed_at": None,
                    "url": source_url,
                }
            ],
        }
    )

    repaired = service._repair_research_references(raw)
    finalized = service._finalize_research_references(
        repaired,
        [],
        accessed_at=datetime(2026, 5, 28, tzinfo=UTC),
    )

    assert len(finalized.dividend_terms.facts) == 1
    assert "Removed 1 unsupported fact(s)." in finalized.dividend_terms.data_gaps[-1]
    assert finalized.references[0].id.startswith("src-")
    assert finalized.references[0].is_verified is False


def test_research_source_id_must_equal_source_url():
    with pytest.raises(ValueError, match="temporary source ID"):
        service._DividendResearchSourceMetadata(
            id="https://other.example/dividend",
            title="Dividend announcement",
            publisher="ASX",
            source_type="Exchange",
            published_at=None,
            accessed_at=None,
            url="https://example.com/dividend",
        )


@pytest.mark.parametrize(
    "response_model",
    [
        service._DividendResearchDraft,
        service._DividendAssessmentDraft,
    ],
)
def test_provider_schema_requires_every_declared_property(response_model):
    schema = ai_helper._openai_compatible_json_schema(response_model.model_json_schema())

    _assert_all_object_properties_are_required(schema)


def test_probability_margin_prevents_weak_winner():
    outcome, rationale = service._resolve_eligible_strategy_recommendation(
        dividend_fixtures.event_context(),
        dividend_fixtures.strategy("DividendCapture", probability=0.65),
        dividend_fixtures.strategy("PostDividendDiscount", probability=0.60),
        "The estimates are close.",
    )

    assert outcome == "NoClearWinner"
    assert "clear probability advantage" in rationale


def test_inconsistent_profit_loss_is_corrected_and_flagged_to_client():
    context = dividend_fixtures.event_context()
    assessment_data = _assessment().model_dump()
    assessment_data["dividend_capture"]["expected_profit_loss_per_share"] = dividend_fixtures.numeric_range(
        0.0,
        1.0,
    ).model_dump()
    assessment = service._DividendAssessmentDraft.model_validate(assessment_data)

    normalized, warnings = service._normalize_strategy_profit_loss(context, assessment)
    analysis = service._build_final_analysis(
        context,
        dividend_fixtures.historical_baseline(),
        _private_research(),
        normalized,
        validation_warnings=tuple(warnings),
    )

    assert normalized.dividend_capture.expected_profit_loss_per_share == dividend_fixtures.numeric_range(2.0, 3.0)
    assert len(warnings) == 1
    assert warnings[0] in normalized.dividend_capture.data_gaps
    assert analysis.analysis_status == "CompleteWithWarnings"
    assert analysis.validation_warnings == warnings
    assert analysis.failure_reason is None


def test_ai_failure_preserves_deterministic_baseline():
    context = dividend_fixtures.event_context()
    baseline = dividend_fixtures.historical_baseline()
    ticker = MagicMock()
    ticker.info = {"quoteType": "EQUITY"}
    ticker.history.return_value = MagicMock()

    with (
        patch.object(service.yf, "Ticker", return_value=ticker),
        patch.object(service, "_resolve_exchange_timezone", return_value=ZoneInfo("Australia/Sydney")),
        patch.object(service, "_normalize_history", return_value=pd.DataFrame()),
        patch.object(service, "_build_event_context", return_value=context),
        patch.object(service, "_calculate_historical_baseline", return_value=baseline),
        patch.object(service, "_research_dividend_event", new_callable=AsyncMock) as mock_research,
        patch.object(service.cache, "generate_key", return_value="cache-key"),
        patch.object(service.cache, "get", new_callable=AsyncMock, return_value=None),
        patch.object(service.cache, "set", new_callable=AsyncMock, return_value=True) as mock_cache_set,
    ):
        mock_research.side_effect = service.DividendEventAIError("Dividend research failed")
        result = asyncio.run(
            service.ai_analyze_div_event(
                symbol="ASX:CBA",
                ex_date=dividend_fixtures.EX_DATE,
                dividend_amount=2.0,
            )
        )

    assert result.analysis_status == "Failed"
    assert result.historical_baseline is baseline
    assert result.dividend_capture is None
    mock_cache_set.assert_awaited_once()
    assert mock_cache_set.await_args.kwargs["ttl"] == 5 * 60


def test_success_adds_required_assumptions_and_recommendation():
    context = dividend_fixtures.event_context()
    baseline = dividend_fixtures.historical_baseline()
    ticker = MagicMock()
    ticker.info = {"quoteType": "EQUITY"}
    ticker.history.return_value = MagicMock()

    with (
        patch.object(service.yf, "Ticker", return_value=ticker),
        patch.object(service, "_resolve_exchange_timezone", return_value=ZoneInfo("Australia/Sydney")),
        patch.object(service, "_normalize_history", return_value=pd.DataFrame()),
        patch.object(service, "_build_event_context", return_value=context),
        patch.object(service, "_calculate_historical_baseline", return_value=baseline),
        patch.object(service, "_research_dividend_event", new_callable=AsyncMock, return_value=_private_research()),
        patch.object(service, "_assess_dividend_event", new_callable=AsyncMock, return_value=_assessment_result()),
        patch.object(service.cache, "generate_key", return_value="cache-key"),
        patch.object(service.cache, "get", new_callable=AsyncMock, return_value=None),
        patch.object(service.cache, "set", new_callable=AsyncMock, return_value=True),
    ):
        result = asyncio.run(
            service.ai_analyze_div_event(
                symbol="ASX:CBA",
                ex_date=dividend_fixtures.EX_DATE,
                dividend_amount=2.0,
            )
        )

    assert result.analysis_status == "Complete"
    assert result.recommendation is not None
    assert result.recommendation.outcome == "DividendCapture"
    assert result.dividend_capture is not None
    assert "Estimates are gross and pre-tax." in result.dividend_capture.assumptions
    assert "Assumed zero round-trip transaction cost for dividend capture." in result.dividend_capture.assumptions


def test_research_uses_structured_task_and_provider_citations():
    context = dividend_fixtures.event_context()
    baseline = dividend_fixtures.historical_baseline()
    source_url = "https://example.com/dividend"
    section = {
        "facts": [{"text": "Supported fact.", "reference_ids": [source_url]}],
        "data_gaps": [],
        "reference_ids": [source_url],
    }
    completion = service._DividendResearchResponse(
        symbol="CBA.AX",
        as_of=datetime(2026, 5, 28, tzinfo=UTC),
        dividend_terms=section,
        issuer_outlook=section,
        event_risks=section,
        market_context=section,
        references=[
            {
                "id": source_url,
                "title": "Dividend announcement",
                "publisher": "ASX",
                "source_type": "Exchange",
                "published_at": None,
                "accessed_at": None,
                "url": source_url,
            }
        ],
    ).model_dump_json()

    with patch.object(
        service.ai_helper,
        "ai_exec_task",
        new_callable=AsyncMock,
        return_value=ai_helper.LLMResponse(
            completion=completion,
            citation_urls=[source_url],
        ),
    ) as mock_exec:
        result = asyncio.run(
            service._research_dividend_event(
                context,
                baseline,
                country="AU",
            )
        )

    assert result.references[0].is_verified is True
    task_id, prompt = mock_exec.await_args.args
    assert task_id == "ANALYZE_DIV_EVENT_RESEARCH"
    assert "INVESTOR_INTENT" not in prompt
    assert mock_exec.await_args.kwargs["response_json_schema"]
