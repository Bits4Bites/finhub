from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.models import ai_portfolio_spotlight as models_spotlight
from tests import portfolio_spotlight_fixtures


@pytest.mark.parametrize(
    ("level", "timing"),
    [
        ("Critical", "AsSoonAsPossibleWithinOneWeek"),
        ("High", "WithinOneToTwoWeeks"),
        ("Medium", "Monitor"),
    ],
)
def test_risk_levels_require_their_action_timing(level, timing):
    risk = portfolio_spotlight_fixtures.risk(
        level=level,
        action_timing=timing,
    )

    assert risk.level == level
    assert risk.action_timing == timing


def test_risk_rejects_low_level():
    data = portfolio_spotlight_fixtures.risk().model_dump()
    data["level"] = "Low"

    with pytest.raises(ValidationError):
        models_spotlight.PortfolioSpotlightRiskAction.model_validate(data)


def test_risk_rejects_inconsistent_action_timing():
    data = portfolio_spotlight_fixtures.risk().model_dump()
    data["action_timing"] = "Monitor"

    with pytest.raises(ValidationError, match="action_timing"):
        models_spotlight.PortfolioSpotlightRiskAction.model_validate(data)


def test_analysis_derives_consistent_rebalance_flag():
    data = portfolio_spotlight_fixtures.analysis().model_dump()
    data["rebalance_recommended"] = "NO"

    with pytest.raises(ValidationError, match="rebalance flag"):
        models_spotlight.PortfolioSpotlightAnalysis.model_validate(data)


def test_analysis_rejects_unknown_affected_ticker():
    data = portfolio_spotlight_fixtures.analysis().model_dump()
    data["risks"][0]["affected_tickers"] = ["NASDAQ:MSFT"]

    with pytest.raises(ValidationError, match="unknown tickers"):
        models_spotlight.PortfolioSpotlightAnalysis.model_validate(data)


def test_empty_portfolio_has_no_snapshot_risks_or_rebalance():
    result = portfolio_spotlight_fixtures.analysis(portfolio_empty=True)

    assert result.portfolio_empty is True
    assert result.snapshot is None
    assert result.risks == []
    assert result.rebalance_recommended == "NO"


def test_snapshot_requires_timezone_aware_as_of():
    data = portfolio_spotlight_fixtures.snapshot().model_dump()
    data["as_of"] = datetime(2026, 8, 21)

    with pytest.raises(ValidationError, match="timezone-aware"):
        models_spotlight.PortfolioSpotlightSnapshot.model_validate(data)


def test_analysis_as_of_is_timezone_aware():
    assert portfolio_spotlight_fixtures.analysis().as_of.tzinfo == UTC
