from datetime import UTC, datetime

from app.models import ai as models_ai
from app.models import ai_portfolio_construction as models_construction
from app.models import portfolio as models_portfolio
from app.services import msai_build_portfolio as service
from app.services import portfolio_verification
from app.utils import ai_reference

SOURCE_URL = "https://example.com/portfolio-research"
SOURCE_ID = ai_reference.generate_source_id(SOURCE_URL)
TICKERS = ["NASDAQ:AAPL", "NASDAQ:MSFT", "NASDAQ:GOOGL"]


def holding(
    ticker: str = "NASDAQ:AAPL",
    *,
    num_shares: float = 10,
) -> models_portfolio.PortfolioHolding:
    return models_portfolio.PortfolioHolding(
        ticker=ticker,
        num_shares=num_shares,
        avg_price=150,
        market_price=200,
        tags="growth",
    )


def verified_portfolio() -> portfolio_verification.VerifiedPortfolio:
    return portfolio_verification.VerifiedPortfolio(
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
                target_allocation=None,
                allocation_drift=None,
                unrealized_profit_loss=500,
                tags="growth",
            )
        ],
        data_gaps=[],
    )


def plan(
    mode: models_construction.PortfolioConstructionMode = "Scratch",
) -> service._PortfolioConstructionPlan:
    return service._PortfolioConstructionPlan(
        construction_mode=mode,
        objective="Construct a diversified growth portfolio.",
        theme_interpretation="Favor durable growth with moderate concentration risk.",
        constraints=["US-listed securities only."],
        selection_criteria=[
            "Durable competitive position.",
            "Evidence of profitable growth.",
            "Complementary portfolio role.",
        ],
        diversification_requirements=[
            "Avoid single-name concentration.",
            "Use complementary business exposures.",
        ],
        seed_strategy="Use verified holdings as context without requiring retention.",
        research_queries=[
            "Current issuer fundamentals.",
            "Material issuer risks.",
            "Portfolio diversification fit.",
        ],
        target_holding_count=3,
        data_gaps=[],
    )


def research_response_data() -> dict[str, object]:
    return {
        "candidates": [
            {
                "ticker": ticker,
                "company_name": company_name,
                "role": role,
                "theme_fit": f"{company_name} supports the requested growth theme.",
                "investment_case": f"{company_name} has a research-supported investment case.",
                "key_risks": ["Valuation and execution risk."],
                "reference_ids": ["research-source"],
            }
            for ticker, company_name, role in zip(
                TICKERS,
                ["Apple Inc.", "Microsoft Corporation", "Alphabet Inc."],
                ["Consumer platform", "Enterprise platform", "Digital services"],
                strict=True,
            )
        ],
        "data_gaps": [],
        "references": [
            {
                "id": "research-source",
                "title": "Portfolio research",
                "publisher": "Example Research",
                "source_type": "Research",
                "published_at": "2026-08-20T00:00:00Z",
                "accessed_at": "2026-08-21T00:00:00Z",
                "url": SOURCE_URL,
            }
        ],
    }


def research() -> service._PortfolioResearch:
    data = research_response_data()
    data["as_of"] = "2026-08-21T00:00:00Z"
    data["references"] = [
        {
            **data["references"][0],
            "id": SOURCE_ID,
            "is_verified": True,
        }
    ]
    for candidate in data["candidates"]:
        candidate["reference_ids"] = [SOURCE_ID]
    return service._PortfolioResearch.model_validate(data)


def draft_data(
    *,
    tickers: list[str] | None = None,
    allocations: list[float] | None = None,
) -> dict[str, object]:
    selected_tickers = tickers or TICKERS
    selected_allocations = allocations or [0.4, 0.35, 0.25]
    return {
        "summary": "A diversified target portfolio aligned with the growth theme.",
        "positions": [
            {
                "ticker": ticker,
                "allocation": allocation,
                "role": f"Portfolio role for {ticker}.",
                "rationale": f"Research supports including {ticker}.",
                "reference_ids": [SOURCE_ID],
            }
            for ticker, allocation in zip(
                selected_tickers,
                selected_allocations,
                strict=True,
            )
        ],
        "overall_data_quality": "High",
        "data_gaps": [],
    }


def reference(*, is_verified: bool = True) -> models_ai.ReferenceSource:
    return models_ai.ReferenceSource(
        id=SOURCE_ID,
        title="Portfolio research",
        publisher="Example Research",
        source_type="Research",
        published_at=datetime(2026, 8, 20, tzinfo=UTC),
        accessed_at=datetime(2026, 8, 21, tzinfo=UTC),
        url=SOURCE_URL,
        is_verified=is_verified,
    )


def construction(
    *,
    mode: models_construction.PortfolioConstructionMode = "Scratch",
) -> models_construction.PortfolioConstruction:
    return models_construction.PortfolioConstruction(
        as_of=datetime(2026, 8, 21, tzinfo=UTC),
        construction_status="Complete",
        construction_mode=mode,
        country="US",
        investor_theme="Durable growth with moderate risk.",
        summary="A diversified target portfolio aligned with the growth theme.",
        verified_seed_holdings=(verified_portfolio().holdings if mode == "Seeded" else []),
        target_portfolio=[
            models_construction.PortfolioTargetPosition(
                ticker=ticker,
                company_name=company_name,
                allocation=allocation,
                role=role,
                rationale=f"Research supports including {ticker}.",
                reference_ids=[SOURCE_ID],
            )
            for ticker, company_name, allocation, role in zip(
                TICKERS,
                ["Apple Inc.", "Microsoft Corporation", "Alphabet Inc."],
                [0.4, 0.35, 0.25],
                ["Consumer platform", "Enterprise platform", "Digital services"],
                strict=True,
            )
        ],
        overall_data_quality="High",
        data_gaps=[],
        validation_warnings=[],
        references=[reference()],
    )
