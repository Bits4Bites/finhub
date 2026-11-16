import copy
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import numpy as np
import pandas as pd

from app.models import ai as models_ai
from app.models import ai_ticker as models_ticker
from app.services import ai_helper
from app.utils import ai_reference

SOURCE_URL = "https://example.com/research/aapl"
SOURCE_ID = ai_reference.generate_source_id(SOURCE_URL)
AS_OF = datetime(2026, 8, 24, 4, 30, tzinfo=UTC)
HORIZONS: tuple[models_ticker.TickerForecastHorizon, ...] = (
    "OneWeek",
    "TwoWeeks",
    "OneMonth",
    "ThreeMonths",
)
_HORIZON_DAYS: dict[models_ticker.TickerForecastHorizon, int] = {
    "OneWeek": 7,
    "TwoWeeks": 14,
    "OneMonth": 30,
    "ThreeMonths": 90,
}
_RESEARCH_SECTION_NAMES = (
    "business_profile",
    "financial_performance",
    "valuation",
    "recent_developments",
    "catalysts",
    "risks",
    "market_consensus",
    "asset_specific",
)


class MarketBoundary:
    def __init__(self, *, quote_type: str = "EQUITY") -> None:
        self.available = True
        self.quote_type = quote_type

    def __call__(self, symbol: str) -> SimpleNamespace:
        if not self.available:
            raise OSError("market boundary unavailable")
        closes = np.full(220, 100.0)
        history = pd.DataFrame(
            {
                "Open": closes,
                "High": closes + 1,
                "Low": closes - 1,
                "Close": closes,
                "Adj Close": closes,
                "Volume": np.full(220, 1_000_000),
            },
            index=pd.date_range(
                end=datetime.now(UTC) - timedelta(days=1),
                periods=220,
                freq="B",
            ),
        )
        return SimpleNamespace(
            info={
                "quoteType": self.quote_type,
                "symbol": "AAPL",
                "fullExchangeName": "NASDAQ",
                "country": "United States",
                "currency": "USD",
                "longName": "Apple Inc.",
                "sector": "Technology",
                "industry": "Consumer Electronics",
                "regularMarketPrice": 100.0,
                "previousClose": 99.0,
                "regularMarketDayLow": 98.0,
                "regularMarketDayHigh": 101.0,
                "fiftyTwoWeekLow": 80.0,
                "fiftyTwoWeekHigh": 120.0,
                "bid": 99.9,
                "ask": 100.1,
                "regularMarketVolume": 1_000_000,
                "marketCap": 3_000_000_000_000,
                "beta": 1.1,
            },
            history=lambda **_kwargs: history.copy(),
        )


def _research_payload() -> dict[str, object]:
    section = {
        "summary": "Evidence-backed section summary.",
        "data_quality": "High",
        "claims": [
            {
                "text": "The cited evidence supports this section.",
                "reference_ids": [SOURCE_URL],
            }
        ],
        "data_gaps": [],
        "reference_ids": [SOURCE_URL],
    }
    return {
        "symbol": "NASDAQ:AAPL",
        **{name: copy.deepcopy(section) for name in _RESEARCH_SECTION_NAMES},
        "data_gaps": [],
        "references": [
            {
                "id": SOURCE_URL,
                "title": "Issuer research",
                "publisher": "Example",
                "source_type": "Research",
                "published_at": AS_OF.isoformat(),
                "accessed_at": None,
                "url": SOURCE_URL,
            }
        ],
    }


def _forecast_payload() -> dict[str, object]:
    return {
        "symbol": "NASDAQ:AAPL",
        "forecasts": [
            {
                "horizon": horizon,
                "assessment_status": "Forecast",
                "expected_price_min": 100.0,
                "expected_price_max": 100.0,
                "confidence": 70,
                "rationale": "The range reflects verified history and sourced research.",
                "key_drivers": ["Revenue growth"],
                "risk_factors": ["Valuation compression"],
                "assumptions": ["No material market disruption"],
                "data_gaps": [],
                "reference_ids": [SOURCE_ID],
            }
            for horizon in HORIZONS
        ],
        "overall_data_quality": "High",
        "data_gaps": [],
    }


def _recommendation_payload() -> dict[str, object]:
    return {
        "action": "HOLD",
        "confidence": 70,
        "summary": "The recommendation reflects the verified evidence and forecasts.",
        "buy_range": None,
        "sell_range": None,
        "reasoning": ["The evidence and forecast ranges support this action."],
        "key_conditions": ["Forecast assumptions remain valid"],
        "reassessment_triggers": ["Material earnings revision"],
        "risk_warnings": ["Market prices can move outside estimated ranges"],
        "reference_ids": [SOURCE_ID],
    }


def make_research_response(*, verified: bool = True) -> ai_helper.LLMResponse:
    return ai_helper.LLMResponse(
        completion=json.dumps(_research_payload()),
        citation_urls=[SOURCE_URL] if verified else [],
    )


def make_forecast_response() -> ai_helper.LLMResponse:
    return ai_helper.LLMResponse(completion=json.dumps(_forecast_payload()))


def make_recommendation_response() -> ai_helper.LLMResponse:
    return ai_helper.LLMResponse(completion=json.dumps(_recommendation_payload()))


def make_ai_responses(
    *,
    verified: bool = True,
    recommendation_count: int = 1,
) -> list[ai_helper.LLMResponse]:
    return [
        make_research_response(verified=verified),
        make_forecast_response(),
        *[make_recommendation_response() for _ in range(recommendation_count)],
    ]


def make_market_snapshot() -> models_ticker.TickerMarketSnapshot:
    return models_ticker.TickerMarketSnapshot(
        as_of=AS_OF,
        symbol="NASDAQ:AAPL",
        company_name="Apple Inc.",
        asset_type="STANDARD",
        exchange="NASDAQ",
        country="US",
        currency="USD",
        sector="Technology",
        industry="Consumer Electronics",
        market_price=100.0,
        previous_close=99.0,
        market_day_low=98.0,
        market_day_high=101.0,
        fifty_two_week_low=80.0,
        fifty_two_week_high=120.0,
        bid=99.9,
        ask=100.1,
        bid_ask_spread_pct=0.2,
        market_volume=1_000_000,
        market_cap=3_000_000_000_000,
        return_5d_pct=1.0,
        return_10d_pct=2.0,
        return_21d_pct=3.0,
        return_63d_pct=4.0,
        realized_volatility_20d_pct=20.0,
        realized_volatility_60d_pct=22.0,
        rsi14=55.0,
        ema_trend_pct=2.0,
        atr14=2.5,
        benchmark_return_21d_pct=1.5,
        peer_return_21d_pct=2.0,
        history_sample_count=500,
        data_gaps=[],
    )


def make_reference(*, verified: bool = True) -> models_ai.ReferenceSource:
    return models_ai.ReferenceSource(
        id=SOURCE_ID,
        title="Issuer research",
        publisher="Example",
        source_type="Research",
        published_at=AS_OF - timedelta(days=1),
        accessed_at=AS_OF,
        url=SOURCE_URL,
        is_verified=verified,
    )


def make_research_section(
    *,
    data_quality: str = "High",
) -> models_ticker.TickerResearchSection:
    return models_ticker.TickerResearchSection(
        summary="Evidence-backed section summary.",
        data_quality=data_quality,
        claims=[
            models_ticker.TickerEvidenceClaim(
                text="The cited evidence supports this section.",
                reference_ids=[SOURCE_ID],
            )
        ],
        data_gaps=[],
        reference_ids=[SOURCE_ID],
    )


def _public_research() -> models_ticker.TickerResearch:
    return models_ticker.TickerResearch(
        as_of=AS_OF,
        business_profile=make_research_section(),
        financial_performance=make_research_section(),
        valuation=make_research_section(),
        recent_developments=make_research_section(),
        catalysts=make_research_section(),
        risks=make_research_section(),
        market_consensus=make_research_section(),
        asset_specific=make_research_section(),
        data_gaps=[],
    )


def _public_forecasts() -> list[models_ticker.TickerPriceForecast]:
    snapshot = make_market_snapshot()
    forecasts = []
    for index, horizon in enumerate(HORIZONS):
        minimum = 101.0 + index
        maximum = 104.0 + index
        forecasts.append(
            models_ticker.TickerPriceForecast(
                horizon=horizon,
                horizon_days=_HORIZON_DAYS[horizon],
                period_end=snapshot.as_of.date() + timedelta(days=_HORIZON_DAYS[horizon]),
                assessment_status="Forecast",
                direction="Flat" if index == 0 else "Up",
                expected_price_min=minimum,
                expected_price_max=maximum,
                expected_return_min_pct=(minimum / snapshot.market_price - 1) * 100,
                expected_return_max_pct=(maximum / snapshot.market_price - 1) * 100,
                confidence=70,
                rationale="The range reflects verified history and sourced research.",
                key_drivers=["Revenue growth"],
                risk_factors=["Valuation compression"],
                assumptions=["No material market disruption"],
                data_gaps=[],
                reference_ids=[SOURCE_ID],
            )
        )
    return forecasts


def make_recommendation(
    *,
    action: str = "HOLD",
    holding: bool = False,
) -> models_ticker.TickerRecommendation:
    buy_range = None
    sell_range = None
    if action == "BUY":
        buy_range = models_ticker.TickerPriceRange(minimum=95.0, maximum=100.0, currency="USD")
    elif action == "SELL":
        sell_range = models_ticker.TickerPriceRange(minimum=104.0, maximum=108.0, currency="USD")
    return models_ticker.TickerRecommendation(
        action=action,
        scope="ExistingHolding" if holding else "NewPosition",
        confidence=70,
        summary="The recommendation reflects the verified evidence and forecasts.",
        buy_range=buy_range,
        sell_range=sell_range,
        reasoning=["The evidence and forecast ranges support this action."],
        key_conditions=["Forecast assumptions remain valid"],
        reassessment_triggers=["Material earnings revision"],
        risk_warnings=["Market prices can move outside estimated ranges"],
        reference_ids=[SOURCE_ID],
    )


def make_analysis(
    *,
    holding: models_ticker.TickerHoldingSnapshot | None = None,
    verified_reference: bool = True,
) -> models_ticker.TickerAnalysis:
    snapshot = make_market_snapshot()
    references = [make_reference(verified=verified_reference)]
    warnings = [] if verified_reference else ["1 cited research source(s) could not be provider-verified."]
    return models_ticker.TickerAnalysis(
        as_of=datetime.now(UTC),
        analysis_status="CompleteWithWarnings" if warnings else "Complete",
        symbol=snapshot.symbol,
        company_name=snapshot.company_name,
        asset_type=snapshot.asset_type,
        exchange=snapshot.exchange,
        country=snapshot.country,
        currency=snapshot.currency,
        market_snapshot=snapshot,
        holding_snapshot=holding,
        research=_public_research(),
        forecasts=_public_forecasts(),
        recommendation=make_recommendation(holding=holding is not None),
        overall_data_quality="High",
        data_gaps=[],
        validation_warnings=warnings,
        references=references,
    )
