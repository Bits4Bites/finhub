from datetime import UTC, datetime

from app.models import ai as models_ai
from app.models import ai_portfolio_spotlight as models_spotlight
from app.models import portfolio as models_portfolio
from app.services import msai_spotlight_portfolio as service


def request_holding(
    ticker: str = "NASDAQ:AAPL",
    *,
    num_shares: float = 10,
) -> models_portfolio.PortfolioHolding:
    return models_portfolio.PortfolioHolding(
        ticker=ticker,
        num_shares=num_shares,
        avg_price=150,
        market_price=190,
        target_allocation=0.6,
        tags="growth",
    )


def snapshot() -> models_spotlight.PortfolioSpotlightSnapshot:
    return models_spotlight.PortfolioSpotlightSnapshot(
        as_of=datetime(2026, 8, 21, tzinfo=UTC),
        country="US",
        currency="USD",
        total_market_value=2000,
        holdings=[
            models_portfolio.PortfolioVerifiedHolding(
                ticker="NASDAQ:AAPL",
                company_name="Apple Inc.",
                exchange="NASDAQ",
                currency="USD",
                num_shares=10,
                avg_price=150,
                market_price=200,
                price_source="MarketData",
                market_value=2000,
                current_allocation=1,
                target_allocation=0.6,
                allocation_drift=0.4,
                unrealized_profit_loss=500,
                tags="growth",
            )
        ],
        data_gaps=[],
    )


def reference(
    source_id: str = "src-reference",
    *,
    is_verified: bool = True,
) -> models_ai.ReferenceSource:
    return models_ai.ReferenceSource(
        id=source_id,
        title="Issuer announcement",
        publisher="Issuer",
        source_type="Issuer",
        published_at=datetime(2026, 8, 20, tzinfo=UTC),
        accessed_at=datetime(2026, 8, 21, tzinfo=UTC),
        url="https://example.com/issuer-announcement",
        is_verified=is_verified,
    )


def risk(
    *,
    level: models_spotlight.PortfolioSpotlightRiskLevel = "Critical",
    action_timing: models_spotlight.PortfolioSpotlightActionTiming = "AsSoonAsPossibleWithinOneWeek",
    requires_rebalance: bool = True,
    reference_ids: list[str] | None = None,
) -> models_spotlight.PortfolioSpotlightRiskAction:
    return models_spotlight.PortfolioSpotlightRiskAction(
        rank=1,
        level=level,
        action_timing=action_timing,
        risk="The portfolio is concentrated in one issuer.",
        action="Reduce the position as soon as possible and within one week.",
        affected_tickers=["NASDAQ:AAPL"],
        requires_rebalance=requires_rebalance,
        confidence=85,
        data_gaps=[],
        reference_ids=reference_ids if reference_ids is not None else ["src-reference"],
    )


def analysis(
    *,
    portfolio_empty: bool = False,
) -> models_spotlight.PortfolioSpotlightAnalysis:
    if portfolio_empty:
        return models_spotlight.PortfolioSpotlightAnalysis(
            as_of=datetime(2026, 8, 21, tzinfo=UTC),
            analysis_status="Complete",
            portfolio_empty=True,
            overall_data_quality="Insufficient",
            snapshot=None,
            risks=[],
            rebalance_recommended="NO",
            data_gaps=["Portfolio has no positions with positive holdings."],
            validation_warnings=[],
            references=[],
        )
    return models_spotlight.PortfolioSpotlightAnalysis(
        as_of=datetime(2026, 8, 21, tzinfo=UTC),
        analysis_status="Complete",
        portfolio_empty=False,
        overall_data_quality="High",
        snapshot=snapshot(),
        risks=[risk()],
        rebalance_recommended="YES",
        data_gaps=[],
        validation_warnings=[],
        references=[reference()],
    )


def research(portfolio_id: str = "portfolio-id") -> service._PortfolioResearch:
    return service._PortfolioResearch.model_validate(
        {
            "portfolio_id": portfolio_id,
            "as_of": "2026-08-21T00:00:00Z",
            "claims": [
                {
                    "category": "Issuer",
                    "text": "Issuer conditions increased portfolio risk.",
                    "affected_tickers": ["NASDAQ:AAPL"],
                    "reference_ids": ["src-reference"],
                }
            ],
            "data_gaps": [],
            "references": [reference().model_dump(mode="python")],
        }
    )


def plan(
    portfolio_id: str = "portfolio-id",
    *,
    investor_theme_present: bool = True,
) -> service._PortfolioAnalysisPlan:
    return service._PortfolioAnalysisPlan(
        portfolio_id=portfolio_id,
        investor_theme_present=investor_theme_present,
        investor_context_summary="Growth-focused investor context." if investor_theme_present else None,
        research_priorities=["Issuer", "Portfolio", "Valuation"],
        assessment_focus=["Assess concentration and alignment with the available investor context."],
        investor_constraints=["Prioritize growth."] if investor_theme_present else [],
        data_gaps=[],
    )


def assessment(portfolio_id: str = "portfolio-id") -> service._PortfolioAssessmentDraft:
    return service._PortfolioAssessmentDraft(
        portfolio_id=portfolio_id,
        as_of=datetime(2026, 8, 21, tzinfo=UTC),
        overall_data_quality="High",
        risks=[risk()],
        data_gaps=[],
    )
