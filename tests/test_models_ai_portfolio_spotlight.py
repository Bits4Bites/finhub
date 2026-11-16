import datetime

import pydantic
import pytest

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
def test_risk_levels_accept_and_serialize_documented_action_timing(level, timing):
    risk = portfolio_spotlight_fixtures.risk(
        level=level,
        action_timing=timing,
    )

    serialized = risk.model_dump(mode="json")
    assert serialized["level"] == level
    assert serialized["action_timing"] == timing


def test_risk_rejects_unsupported_level():
    data = portfolio_spotlight_fixtures.risk().model_dump(mode="python")
    data["level"] = "Low"

    with pytest.raises(pydantic.ValidationError):
        models_spotlight.PortfolioSpotlightRiskAction.model_validate(data)


def test_risk_rejects_timing_inconsistent_with_level():
    data = portfolio_spotlight_fixtures.risk().model_dump(mode="python")
    data["action_timing"] = "Monitor"

    with pytest.raises(pydantic.ValidationError):
        models_spotlight.PortfolioSpotlightRiskAction.model_validate(data)


def test_risk_normalizes_canonical_affected_ticker():
    data = portfolio_spotlight_fixtures.risk().model_dump(mode="python")
    data["affected_tickers"] = [" nasdaq:aapl "]

    risk = models_spotlight.PortfolioSpotlightRiskAction.model_validate(data)

    assert risk.affected_tickers == ["NASDAQ:AAPL"]


def test_risk_rejects_noncanonical_affected_ticker():
    data = portfolio_spotlight_fixtures.risk().model_dump(mode="python")
    data["affected_tickers"] = ["AAPL"]

    with pytest.raises(pydantic.ValidationError):
        models_spotlight.PortfolioSpotlightRiskAction.model_validate(data)


def test_analysis_rejects_rebalance_flag_inconsistent_with_risks():
    data = portfolio_spotlight_fixtures.analysis().model_dump(mode="python")
    data["rebalance_recommended"] = "NO"

    with pytest.raises(pydantic.ValidationError):
        models_spotlight.PortfolioSpotlightAnalysis.model_validate(data)


def test_analysis_rejects_unknown_affected_ticker():
    data = portfolio_spotlight_fixtures.analysis().model_dump(mode="python")
    data["risks"][0]["affected_tickers"] = ["NASDAQ:MSFT"]

    with pytest.raises(pydantic.ValidationError):
        models_spotlight.PortfolioSpotlightAnalysis.model_validate(data)


def test_analysis_rejects_unknown_referenced_source():
    data = portfolio_spotlight_fixtures.analysis().model_dump(mode="python")
    data["risks"][0]["reference_ids"] = ["src-unknown"]

    with pytest.raises(pydantic.ValidationError):
        models_spotlight.PortfolioSpotlightAnalysis.model_validate(data)


def test_empty_portfolio_serializes_without_snapshot_risks_or_rebalance():
    result = portfolio_spotlight_fixtures.analysis(portfolio_empty=True)

    serialized = result.model_dump(mode="json")
    assert serialized["portfolio_empty"] is True
    assert serialized["snapshot"] is None
    assert serialized["risks"] == []
    assert serialized["rebalance_recommended"] == "NO"


def test_snapshot_rejects_naive_as_of_timestamp():
    data = portfolio_spotlight_fixtures.snapshot().model_dump(mode="python")
    data["as_of"] = datetime.datetime(2026, 8, 21)

    with pytest.raises(pydantic.ValidationError):
        models_spotlight.PortfolioSpotlightSnapshot.model_validate(data)


def test_snapshot_normalizes_iso_country_and_currency_codes():
    data = portfolio_spotlight_fixtures.snapshot().model_dump(mode="python")
    data["country"] = " us "
    data["currency"] = " usd "
    data["holdings"][0]["currency"] = " usd "

    snapshot = models_spotlight.PortfolioSpotlightSnapshot.model_validate(data)

    assert snapshot.country == "US"
    assert snapshot.currency == "USD"
    assert snapshot.holdings[0].currency == "USD"


@pytest.mark.parametrize(("field", "value"), [("country", "ZZ"), ("currency", "U$D")])
def test_snapshot_rejects_invalid_identifier(field, value):
    data = portfolio_spotlight_fixtures.snapshot().model_dump(mode="python")
    data[field] = value

    with pytest.raises(pydantic.ValidationError):
        models_spotlight.PortfolioSpotlightSnapshot.model_validate(data)


def test_snapshot_rejects_holding_currency_mismatch():
    data = portfolio_spotlight_fixtures.snapshot().model_dump(mode="python")
    data["currency"] = "AUD"

    with pytest.raises(pydantic.ValidationError):
        models_spotlight.PortfolioSpotlightSnapshot.model_validate(data)


def test_analysis_preserves_timezone_aware_as_of_timestamp():
    analysis = portfolio_spotlight_fixtures.analysis()

    assert analysis.as_of.tzinfo == datetime.UTC
    assert analysis.model_dump(mode="json")["as_of"].endswith("Z")
