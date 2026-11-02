from datetime import UTC, datetime, timedelta

from app.models import ai as models_ai
from app.models import ai_ticker as models_ticker
from app.services import msai_analyze_ticker as services_ticker
from app.utils import ai_reference

SOURCE_URL = "https://example.com/research/aapl"
SOURCE_ID = ai_reference.generate_source_id(SOURCE_URL)
AS_OF = datetime(2026, 8, 24, 4, 30, tzinfo=UTC)


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


def make_baseline() -> services_ticker._TickerMarketBaseline:
    return services_ticker._TickerMarketBaseline(
        snapshot=make_market_snapshot(),
        forecast_envelopes=[
            services_ticker._ForecastEnvelope(
                horizon=horizon,
                expected_price_min=80.0,
                expected_price_max=125.0,
                sample_count=400,
                data_gaps=[],
            )
            for horizon in services_ticker._HORIZON_ORDER
        ],
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


def make_research(
    *,
    verified: bool = True,
) -> services_ticker._TickerResearch:
    sections = {section_name: make_research_section() for section_name in services_ticker._RESEARCH_SECTION_NAMES}
    return services_ticker._TickerResearch(
        symbol="NASDAQ:AAPL",
        as_of=AS_OF,
        data_gaps=[],
        references=[make_reference(verified=verified)],
        **sections,
    )


def make_forecasts() -> services_ticker._ValidatedForecasts:
    snapshot = make_market_snapshot()
    forecasts = []
    for index, horizon in enumerate(services_ticker._HORIZON_ORDER):
        minimum = 101.0 + index
        maximum = 104.0 + index
        forecasts.append(
            models_ticker.TickerPriceForecast(
                horizon=horizon,
                horizon_days=services_ticker._HORIZON_DAYS[horizon],
                period_end=snapshot.as_of.date() + timedelta(days=services_ticker._HORIZON_DAYS[horizon]),
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
    return services_ticker._ValidatedForecasts(
        forecasts=forecasts,
        overall_data_quality="High",
        data_gaps=[],
    )


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
    return services_ticker._build_analysis(
        make_market_snapshot(),
        make_research(verified=verified_reference),
        make_forecasts(),
        make_recommendation(holding=holding is not None),
        holding_snapshot=holding,
    )
