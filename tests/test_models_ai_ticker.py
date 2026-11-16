import pydantic
import pytest

from app.models import ai_ticker as models_ticker
from app.schemas import ai_ticker as schemas_ticker
from tests import ticker_fixtures


def _holding_snapshot_data() -> dict[str, object]:
    return {
        "num_shares": 10,
        "avg_price": 80,
        "currency": "USD",
        "market_price": 100,
        "cost_basis": 800,
        "market_value": 1000,
        "unrealized_profit_loss": 200,
        "unrealized_return_pct": 25,
        "break_even_price": 80,
    }


def test_ticker_price_range_normalizes_currency_and_serializes():
    price_range = models_ticker.TickerPriceRange(
        minimum=95,
        maximum=100,
        currency=" usd ",
    )

    assert price_range.model_dump(mode="json") == {
        "minimum": 95.0,
        "maximum": 100.0,
        "currency": "USD",
    }


def test_ticker_price_range_rejects_reversed_bounds():
    with pytest.raises(pydantic.ValidationError):
        models_ticker.TickerPriceRange(minimum=101, maximum=100, currency="USD")


def test_ticker_price_range_rejects_non_alpha_currency_code():
    with pytest.raises(pydantic.ValidationError):
        models_ticker.TickerPriceRange(minimum=95, maximum=100, currency="U$D")


def test_market_snapshot_normalizes_canonical_identifiers_and_serializes():
    data = ticker_fixtures.make_market_snapshot().model_dump(mode="python")
    data.update(
        {
            "symbol": " nasdaq:aapl ",
            "exchange": " nms ",
            "country": " us ",
            "currency": " usd ",
        }
    )

    snapshot = models_ticker.TickerMarketSnapshot.model_validate(data)

    serialized = snapshot.model_dump(mode="json")
    assert serialized["symbol"] == "NASDAQ:AAPL"
    assert serialized["exchange"] == "NASDAQ"
    assert serialized["country"] == "US"
    assert serialized["currency"] == "USD"


def test_market_snapshot_rejects_symbol_without_exchange():
    data = ticker_fixtures.make_market_snapshot().model_dump(mode="python")
    data["symbol"] = "AAPL"

    with pytest.raises(pydantic.ValidationError):
        models_ticker.TickerMarketSnapshot.model_validate(data)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("exchange", "NYSE"),
        ("country", "ZZ"),
        ("currency", "U$D"),
    ],
)
def test_market_snapshot_rejects_invalid_identifier(field, value):
    data = ticker_fixtures.make_market_snapshot().model_dump(mode="python")
    data[field] = value

    with pytest.raises(pydantic.ValidationError):
        models_ticker.TickerMarketSnapshot.model_validate(data)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("market_day_low", 102),
        ("fifty_two_week_low", 121),
        ("bid", 101),
    ],
)
def test_market_snapshot_rejects_reversed_documented_price_bounds(field, value):
    data = ticker_fixtures.make_market_snapshot().model_dump(mode="python")
    data[field] = value

    with pytest.raises(pydantic.ValidationError):
        models_ticker.TickerMarketSnapshot.model_validate(data)


def test_market_snapshot_rejects_spread_inconsistent_with_bid_and_ask():
    data = ticker_fixtures.make_market_snapshot().model_dump(mode="python")
    data["bid_ask_spread_pct"] = 1.0

    with pytest.raises(pydantic.ValidationError):
        models_ticker.TickerMarketSnapshot.model_validate(data)


def test_holding_snapshot_accepts_and_serializes_consistent_calculations():
    holding = models_ticker.TickerHoldingSnapshot.model_validate(_holding_snapshot_data())

    assert holding.model_dump(mode="json") == {
        "num_shares": 10.0,
        "avg_price": 80.0,
        "currency": "USD",
        "market_price": 100.0,
        "cost_basis": 800.0,
        "market_value": 1000.0,
        "unrealized_profit_loss": 200.0,
        "unrealized_return_pct": 25.0,
        "break_even_price": 80.0,
    }


def test_holding_snapshot_rejects_inconsistent_market_value():
    data = _holding_snapshot_data()
    data["market_value"] = 999

    with pytest.raises(pydantic.ValidationError):
        models_ticker.TickerHoldingSnapshot.model_validate(data)


def test_holding_snapshot_rejects_non_alpha_currency_code():
    data = _holding_snapshot_data()
    data["currency"] = "U$D"

    with pytest.raises(pydantic.ValidationError):
        models_ticker.TickerHoldingSnapshot.model_validate(data)


def test_research_section_accepts_claim_reference_ids_and_serializes():
    section = ticker_fixtures.make_research_section()

    serialized = section.model_dump(mode="json")
    assert set(serialized["reference_ids"]) == set(serialized["claims"][0]["reference_ids"])


def test_research_section_rejects_reference_ids_not_used_by_claims():
    data = ticker_fixtures.make_research_section().model_dump(mode="python")
    data["reference_ids"] = ["src-other"]

    with pytest.raises(pydantic.ValidationError):
        models_ticker.TickerResearchSection.model_validate(data)


def test_forecast_rejects_horizon_days_inconsistent_with_horizon():
    data = ticker_fixtures.make_analysis().forecasts[0].model_dump(mode="python")
    data["horizon_days"] = 8

    with pytest.raises(pydantic.ValidationError):
        models_ticker.TickerPriceForecast.model_validate(data)


def test_buy_recommendation_requires_buy_range():
    recommendation = ticker_fixtures.make_recommendation(action="BUY")
    assert recommendation.model_dump(mode="json")["buy_range"] is not None

    data = recommendation.model_dump(mode="python")
    data["buy_range"] = None
    with pytest.raises(pydantic.ValidationError):
        models_ticker.TickerRecommendation.model_validate(data)


def test_ticker_analysis_accepts_and_serializes_referenced_sources():
    analysis = ticker_fixtures.make_analysis()

    serialized = analysis.model_dump(mode="json")
    source_id = serialized["references"][0]["id"]
    assert serialized["symbol"] == "NASDAQ:AAPL"
    assert source_id in serialized["recommendation"]["reference_ids"]
    assert source_id in serialized["forecasts"][0]["reference_ids"]
    assert source_id in serialized["research"]["business_profile"]["reference_ids"]


def test_ticker_analysis_rejects_unknown_referenced_source():
    data = ticker_fixtures.make_analysis().model_dump(mode="python")
    data["recommendation"]["reference_ids"] = ["src-unknown"]

    with pytest.raises(pydantic.ValidationError):
        models_ticker.TickerAnalysis.model_validate(data)


def test_ticker_analysis_rejects_forecasts_outside_documented_order():
    data = ticker_fixtures.make_analysis().model_dump(mode="python")
    data["forecasts"][0], data["forecasts"][1] = data["forecasts"][1], data["forecasts"][0]

    with pytest.raises(pydantic.ValidationError):
        models_ticker.TickerAnalysis.model_validate(data)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("period_end", "2026-12-31"),
        ("expected_return_min_pct", 99),
        ("direction", "Down"),
    ],
)
def test_ticker_analysis_rejects_inconsistent_forecast_calculation(field, value):
    data = ticker_fixtures.make_analysis().model_dump(mode="python")
    data["forecasts"][0][field] = value

    with pytest.raises(pydantic.ValidationError):
        models_ticker.TickerAnalysis.model_validate(data)


@pytest.mark.parametrize(("field", "value"), [("exchange", "NYSE"), ("country", "AU")])
def test_ticker_analysis_rejects_identity_that_differs_from_snapshot(field, value):
    data = ticker_fixtures.make_analysis().model_dump(mode="python")
    data[field] = value

    with pytest.raises(pydantic.ValidationError):
        models_ticker.TickerAnalysis.model_validate(data)


def test_ticker_analysis_rejects_holding_currency_that_differs_from_snapshot():
    data = ticker_fixtures.make_analysis().model_dump(mode="python")
    holding_data = _holding_snapshot_data()
    holding_data["currency"] = "AUD"
    data["holding_snapshot"] = holding_data
    data["recommendation"]["scope"] = "ExistingHolding"

    with pytest.raises(pydantic.ValidationError):
        models_ticker.TickerAnalysis.model_validate(data)


def test_analyze_ticker_request_normalizes_and_serializes_symbol():
    request = schemas_ticker.AnalyzeTickerRequest(
        symbol=" nasdaq:aapl ",
        current_holding={"num_shares": 10, "avg_price": 80},
    )

    assert request.model_dump(mode="json") == {
        "symbol": "NASDAQ:AAPL",
        "current_holding": {
            "num_shares": 10.0,
            "avg_price": 80.0,
        },
    }


def test_analyze_ticker_request_rejects_embedded_whitespace():
    with pytest.raises(pydantic.ValidationError):
        schemas_ticker.AnalyzeTickerRequest(symbol="NASDAQ:AA PL")


@pytest.mark.parametrize("symbol", [":AAPL", "NASDAQ:", "NASDAQ:AAPL:US"])
def test_analyze_ticker_request_rejects_malformed_exchange_qualified_symbol(symbol):
    with pytest.raises(pydantic.ValidationError):
        schemas_ticker.AnalyzeTickerRequest(symbol=symbol)
