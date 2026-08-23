from __future__ import annotations

from datetime import UTC, datetime

from app.models import ai as models_ai
from app.models import ai_portfolio_construction as models_construction
from app.models import ai_portfolio_review as models_review
from app.models import portfolio as models_portfolio
from app.services import msai_review_portfolio as service
from app.services import portfolio_verification
from app.utils import ai_reference

TICKERS = ["NASDAQ:AAPL", "NASDAQ:MSFT", "NASDAQ:GOOGL"]
COMPANY_NAMES = ["Apple Inc.", "Microsoft Corporation", "Alphabet Inc."]
SOURCE_URLS = [
    "https://example.com/aapl",
    "https://example.com/msft",
    "https://example.com/googl",
]
SOURCE_IDS = [ai_reference.generate_source_id(url) for url in SOURCE_URLS]


def holdings() -> list[models_portfolio.PortfolioHolding]:
    return [
        models_portfolio.PortfolioHolding(
            ticker=ticker,
            num_shares=quantity,
            avg_price=average_price,
            market_price=market_price,
        )
        for ticker, quantity, average_price, market_price in zip(
            TICKERS,
            [10, 5, 4],
            [80, 100, 90],
            [100, 120, 100],
            strict=True,
        )
    ]


def verified_portfolio() -> portfolio_verification.VerifiedPortfolio:
    values = [1000, 600, 400]
    total = sum(values)
    return portfolio_verification.VerifiedPortfolio(
        as_of=datetime(2026, 8, 23, tzinfo=UTC),
        country="US",
        currency="USD",
        total_market_value=total,
        holdings=[
            models_portfolio.PortfolioVerifiedHolding(
                ticker=ticker,
                company_name=company_name,
                exchange="NASDAQ",
                currency="USD",
                num_shares=quantity,
                avg_price=average_price,
                market_price=market_price,
                price_source="MarketData",
                market_value=market_value,
                current_allocation=market_value / total,
                target_allocation=None,
                allocation_drift=None,
                unrealized_profit_loss=(market_price - average_price) * quantity,
                tags=None,
            )
            for ticker, company_name, quantity, average_price, market_price, market_value in zip(
                TICKERS,
                COMPANY_NAMES,
                [10, 5, 4],
                [80, 100, 90],
                [100, 120, 100],
                values,
                strict=True,
            )
        ],
        data_gaps=[],
    )


def snapshot() -> models_review.PortfolioReviewSnapshot:
    return models_review.PortfolioReviewSnapshot.model_validate(verified_portfolio().model_dump())


def total_budget(amount: float = 500) -> models_construction.PortfolioBudget:
    return models_construction.PortfolioBudget(
        budget_type="Total",
        is_inferred=False,
        amount=amount,
        currency="USD",
        frequency=None,
        source_text=f"Total budget USD {amount:g}",
    )


def plan(
    *,
    portfolio_id: str = "portfolio-id",
    budget: models_construction.PortfolioBudget | None = None,
    strategy: models_review.PortfolioReviewStrategy = "LongTerm",
) -> service._PortfolioReviewPlan:
    return service._PortfolioReviewPlan(
        portfolio_id=portfolio_id,
        strategy=strategy,
        budget=budget or total_budget(),
        objective="Review alignment with durable long-term growth.",
        theme_interpretation="Favor durable compounding with controlled concentration.",
        research_priorities=["Issuer", "Portfolio", "Valuation"],
        strength_questions=["Which holdings provide durable quality?"],
        risk_questions=["Where is concentration material?", "Which issuer risks challenge the thesis?"],
        holding_questions=["Does each thesis remain intact?", "What role does each holding serve?"],
        target_design_questions=["Which weights improve alignment?", "Can new cash fund the target?"],
        candidate_addition_queries=[],
        data_gaps=[],
    )


def research_response_data(*, portfolio_id: str = "portfolio-id") -> dict[str, object]:
    return {
        "portfolio_id": portfolio_id,
        "claims": [
            {
                "category": "Issuer",
                "text": f"Current evidence supports a decision-useful review of {ticker}.",
                "affected_tickers": [ticker],
                "reference_ids": [url],
            }
            for ticker, url in zip(TICKERS, SOURCE_URLS, strict=True)
        ],
        "additions": [],
        "data_gaps": [],
        "references": [
            {
                "id": url,
                "title": f"{company_name} research",
                "publisher": "Example Research",
                "source_type": "Research",
                "published_at": "2026-08-22T00:00:00Z",
                "accessed_at": None,
                "url": url,
            }
            for company_name, url in zip(COMPANY_NAMES, SOURCE_URLS, strict=True)
        ],
    }


def research(*, portfolio_id: str = "portfolio-id") -> service._PortfolioResearch:
    data = research_response_data(portfolio_id=portfolio_id)
    data["as_of"] = "2026-08-23T00:00:00Z"
    data["references"] = [
        {
            **reference,
            "id": source_id,
            "accessed_at": "2026-08-23T00:00:00Z",
            "is_verified": True,
        }
        for reference, source_id in zip(data["references"], SOURCE_IDS, strict=True)
    ]
    for claim, source_id in zip(data["claims"], SOURCE_IDS, strict=True):
        claim["reference_ids"] = [source_id]
    return service._PortfolioResearch.model_validate(data)


def assessment_data(*, portfolio_id: str = "portfolio-id") -> dict[str, object]:
    return {
        "portfolio_id": portfolio_id,
        "summary": "The portfolio has strong quality exposure with manageable concentration risk.",
        "strengths": [
            {
                "title": "Durable platforms",
                "analysis": "The current holdings provide established platform exposure.",
                "affected_tickers": ["NASDAQ:AAPL", "NASDAQ:MSFT"],
                "confidence": 85,
                "data_gaps": [],
                "reference_ids": SOURCE_IDS[:2],
            }
        ],
        "risks": [
            {
                "level": "Medium",
                "risk": "Technology concentration can amplify correlated drawdowns.",
                "impact": "A sector-wide repricing could affect all three holdings.",
                "mitigation": "Direct new cash according to the validated target and monitor concentration.",
                "affected_tickers": TICKERS,
                "confidence": 80,
                "data_gaps": [],
                "reference_ids": SOURCE_IDS,
            }
        ],
        "holding_reviews": [
            {
                "ticker": ticker,
                "role_category": role_category,
                "role_description": role_description,
                "thesis": f"The current evidence supports retaining {ticker}.",
                "strengths": ["Established competitive position."],
                "risks": ["Valuation and execution remain relevant."],
                "recommendation": recommendation,
                "exit_reason": None,
                "confidence": 82,
                "data_gaps": [],
                "reference_ids": [source_id],
            }
            for ticker, role_category, role_description, recommendation, source_id in zip(
                TICKERS,
                ["CoreGrowth", "DefensiveIncome", "Diversifier"],
                ["Core growth compounder", "Defensive earnings quality", "Digital portfolio diversifier"],
                ["BUY_MORE", "HOLD", "BUY_MORE"],
                SOURCE_IDS,
                strict=True,
            )
        ],
        "eligible_additions": [],
        "overall_data_quality": "High",
        "data_gaps": [],
    }


def assessment(*, portfolio_id: str = "portfolio-id") -> service._PortfolioAssessmentDraft:
    return service._PortfolioAssessmentDraft.model_validate(assessment_data(portfolio_id=portfolio_id))


def target_data(*, portfolio_id: str = "portfolio-id") -> dict[str, object]:
    return {
        "portfolio_id": portfolio_id,
        "summary": "Use new cash to move gradually toward the target.",
        "positions": [
            {
                "ticker": ticker,
                "allocation": allocation,
                "role_category": role_category,
                "role_description": role_description,
                "rationale": f"The evidence supports the target weight for {ticker}.",
                "reference_ids": [source_id],
            }
            for ticker, allocation, role_category, role_description, source_id in zip(
                TICKERS,
                [0.52, 0.28, 0.20],
                ["CoreGrowth", "DefensiveIncome", "Diversifier"],
                ["Core growth compounder", "Defensive earnings quality", "Digital portfolio diversifier"],
                SOURCE_IDS,
                strict=True,
            )
        ],
        "data_gaps": [],
    }


def target(*, portfolio_id: str = "portfolio-id") -> service._PortfolioTargetDraft:
    return service._PortfolioTargetDraft.model_validate(target_data(portfolio_id=portfolio_id))


def target_positions() -> list[models_review.PortfolioReviewTargetPosition]:
    return service._build_target_positions(
        snapshot=snapshot(),
        research=research(),
        assessment=assessment(),
        target_draft=target(),
    )


def holding_reviews() -> list[models_review.PortfolioHoldingReview]:
    return service._build_holding_reviews(
        snapshot=snapshot(),
        assessment=assessment(),
        target_positions=target_positions(),
        strategy="LongTerm",
    )


def reference(index: int) -> models_ai.ReferenceSource:
    return research().references[index]


def review(*, action_plan: bool = True) -> models_review.PortfolioReview:
    target_items = target_positions()
    holding_items = holding_reviews()
    actions = [
        models_review.PortfolioReviewAction(
            priority=priority,
            action=action,
            ticker=ticker,
            company_name=company_name,
            current_allocation=current_allocation,
            target_allocation=target_allocation,
            quantity=quantity,
            market_price=market_price,
            estimated_amount=estimated_amount,
            instruction=instruction,
            reasoning=f"{action} advances the validated target.",
            reference_ids=[source_id],
        )
        for (
            priority,
            action,
            ticker,
            company_name,
            current_allocation,
            target_allocation,
            quantity,
            market_price,
            estimated_amount,
            instruction,
            source_id,
        ) in [
            (
                1,
                "BUY_MORE",
                TICKERS[0],
                COMPANY_NAMES[0],
                0.5,
                0.52,
                3,
                100,
                300,
                "BUY 3 additional whole shares.",
                SOURCE_IDS[0],
            ),
            (
                2,
                "BUY_MORE",
                TICKERS[2],
                COMPANY_NAMES[2],
                0.2,
                0.2,
                1,
                100,
                100,
                "BUY 1 additional whole share.",
                SOURCE_IDS[2],
            ),
            (
                3,
                "HOLD",
                TICKERS[1],
                COMPANY_NAMES[1],
                0.3,
                0.28,
                None,
                120,
                None,
                "HOLD the current 5 whole shares.",
                SOURCE_IDS[1],
            ),
        ]
    ]
    plan = (
        models_review.PortfolioReviewActionPlan(
            plan_type="Growth",
            budget=total_budget(),
            cash_ledger=models_review.PortfolioReviewCashLedger(
                new_money_budget=500,
                estimated_sale_proceeds=0,
                purchase_spend=400,
                unallocated_cash=100,
            ),
            summary="Buy the underweight positions and retain unallocated cash.",
            actions=actions,
        )
        if action_plan
        else None
    )
    return models_review.PortfolioReview(
        as_of=datetime(2026, 8, 23, tzinfo=UTC),
        review_status="Complete",
        strategy="LongTerm",
        country="US",
        investor_theme="Long-term growth. Total budget USD 500.",
        snapshot=snapshot(),
        budget=total_budget(),
        summary=assessment().summary,
        strengths=[models_review.PortfolioReviewStrength.model_validate(assessment().strengths[0].model_dump())],
        risks=[models_review.PortfolioReviewRisk.model_validate(assessment().risks[0].model_dump())],
        holding_reviews=holding_items,
        target_portfolio=target_items,
        target_turnover=0.02,
        rebalance_requested=False,
        rebalance_recommended="NO",
        major_rebalance_reasons=[],
        action_plan=plan,
        overall_data_quality="High",
        data_gaps=[],
        validation_warnings=[],
        references=research().references,
    )
