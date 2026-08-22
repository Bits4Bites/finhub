from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Self

from pydantic import ConfigDict, Field, model_validator

from ..utils import ai_reference as ai_reference_utils
from . import ai as models_ai
from . import event
from . import types as models_types

ListingStatus = Literal["Upcoming", "Listed"]
ListingStance = Literal["Bullish", "Neutral", "Bearish", "InsufficientData"]
ListingAnalysisStatus = Literal["NotStarted", "Completed", "Failed"]
ListingOutlookAssessmentType = Literal["Forecast", "Observed", "InsufficientData"]
ListingOutlookDirection = Literal["Up", "Flat", "Down", "InsufficientData"]
ListingRiskSeverity = Literal["Critical", "High", "Medium", "Low"]
ListingLikelihood = Literal["High", "Medium", "Low"]
ListingHorizon = Literal["IPO Day", "First Week", "First Two Weeks", "First Month", "Longer Term"]


class ListingEvidenceClaim(models_ai.StrictAIModel):
    """One factual claim used in a new-listing analysis."""

    text: models_types.NonEmptyString = Field(description="Factual evidence statement.")
    reference_ids: list[models_types.NonEmptyString] = Field(
        min_length=1,
        description="Identifiers of sources supporting the claim.",
    )


class ListingEvidenceSection(models_ai.StrictAIModel):
    """A group of sourced listing facts and known evidence gaps."""

    facts: list[ListingEvidenceClaim] = Field(description="Sourced facts relevant to this analysis section.")
    data_gaps: list[str] = Field(description="Missing, unavailable, or conflicting evidence for the section.")
    reference_ids: list[models_types.NonEmptyString] = Field(
        min_length=1,
        description="Identifiers of all sources used by the section.",
    )


class ListingAnalysisSection(ListingEvidenceSection):
    """Common assessment content shared by listing-analysis sections."""

    summary: models_types.NonEmptyString = Field(description="Concise conclusion for the analysis section.")
    data_quality: models_types.DataQuality = Field(description="Quality of the evidence supporting the section.")
    assumptions: list[str] = Field(description="Assumptions used when interpreting available evidence.")


class ListingOfferAnalysis(ListingAnalysisSection):
    """Assessment of the listing offer structure and capital raising."""

    issue_price_assessment: models_types.NonEmptyString = Field(description="Assessment of the offered issue price.")
    capital_raise_assessment: models_types.NonEmptyString = Field(
        description="Assessment of the amount and structure of capital raised."
    )
    underwriting_assessment: models_types.NonEmptyString = Field(
        description="Assessment of underwriting support and execution risk."
    )
    use_of_funds: list[str] = Field(description="Material stated uses of listing proceeds.")
    dilution_and_escrow: str | None = Field(
        description="Assessment of dilution, escrow, and lock-up effects, when available."
    )


class ListingBusinessAnalysis(ListingAnalysisSection):
    """Assessment of the issuer's business model and competitive context."""

    business_model: models_types.NonEmptyString = Field(
        description="Description and assessment of how the issuer creates value."
    )
    revenue_sources: list[str] = Field(description="Material sources of issuer revenue.")
    competitive_position: models_types.NonEmptyString = Field(
        description="Assessment of the issuer's competitive position."
    )
    sector_context: models_types.NonEmptyString = Field(description="Relevant sector conditions affecting the issuer.")


class ListingFinancialAnalysis(ListingAnalysisSection):
    """Assessment of issuer financial performance and funding quality."""

    historical_performance: models_types.NonEmptyString = Field(
        description="Assessment of available historical financial performance."
    )
    profitability_and_cash_flow: models_types.NonEmptyString = Field(
        description="Assessment of profitability and cash-flow characteristics."
    )
    balance_sheet_and_funding: models_types.NonEmptyString = Field(
        description="Assessment of balance-sheet strength and funding requirements."
    )
    forecast_quality: models_types.NonEmptyString = Field(
        description="Assessment of management forecasts and their supporting evidence."
    )


class ListingValuationAnalysis(ListingAnalysisSection):
    """Assessment of listing valuation and sensitivity."""

    valuation_view: models_types.NonEmptyString = Field(description="Overall view of the offer valuation.")
    implied_market_cap: float | None = Field(
        description="Implied market capitalization at the issue price, when derivable."
    )
    peer_comparison: models_types.NonEmptyString = Field(description="Comparison with relevant listed peers.")
    sensitivity: models_types.NonEmptyString = Field(
        description="Key assumptions and variables to which valuation is sensitive."
    )


class ListingGovernanceAnalysis(ListingAnalysisSection):
    """Assessment of issuer leadership, ownership, and governance."""

    board_and_management: models_types.NonEmptyString = Field(
        description="Assessment of board and management experience and suitability."
    )
    ownership_and_escrow: models_types.NonEmptyString = Field(
        description="Assessment of post-listing ownership, escrow, and lock-up arrangements."
    )
    governance_concerns: list[str] = Field(
        description="Material governance concerns identified from available evidence."
    )


class ListingDriver(models_ai.StrictAIModel):
    """Common evidence-linked driver affecting a new listing."""

    title: models_types.NonEmptyString = Field(description="Short label for the driver.")
    description: models_types.NonEmptyString = Field(
        description="Explanation of how the driver may affect the listing."
    )
    likelihood: ListingLikelihood = Field(description="Estimated likelihood that the driver will materialize.")
    horizon: ListingHorizon = Field(description="Period over which the driver is relevant.")
    reference_ids: list[models_types.NonEmptyString] = Field(
        min_length=1,
        description="Identifiers of sources supporting the driver.",
    )


class ListingRisk(ListingDriver):
    """A material downside driver for a new listing."""

    severity: ListingRiskSeverity = Field(description="Potential impact severity of the risk.")


class ListingCatalyst(ListingDriver):
    """A potential positive catalyst for a new listing."""


class ListingRiskCatalystAnalysis(ListingAnalysisSection):
    """Assessment of material listing risks and positive catalysts."""

    risks: list[ListingRisk] = Field(description="Material downside risks for the listing.")
    catalysts: list[ListingCatalyst] = Field(description="Potential positive catalysts for the listing.")


class ListingPeriodOutlook(models_ai.StrictAIModel):
    """Observed or forecast listing performance for a defined period."""

    assessment_type: ListingOutlookAssessmentType = Field(
        description="Whether the outlook is observed, forecast, or unavailable."
    )
    period_end: date | None = Field(description="End date of the assessment period, or null when unavailable.")
    direction: ListingOutlookDirection = Field(description="Expected or observed price direction over the period.")
    expected_price_min: float | None = Field(description="Lower expected or observed price bound, when available.")
    expected_price_max: float | None = Field(description="Upper expected or observed price bound, when available.")
    expected_return_min_pct: float | None = Field(description="Lower expected or observed percentage-return bound.")
    expected_return_max_pct: float | None = Field(description="Upper expected or observed percentage-return bound.")
    confidence: int = Field(
        ge=0,
        le=100,
        description="Confidence score for the outlook from zero through 100.",
    )
    rationale: models_types.NonEmptyString = Field(description="Evidence-based explanation of the period outlook.")
    key_drivers: list[str] = Field(description="Factors expected to drive the period outcome.")
    risk_factors: list[str] = Field(description="Factors that could impair the period outcome.")
    assumptions: list[str] = Field(description="Assumptions underlying the outlook.")
    data_gaps: list[str] = Field(description="Missing or uncertain information affecting the outlook.")
    reference_ids: list[models_types.NonEmptyString] = Field(
        min_length=1,
        description="Identifiers of sources supporting the outlook.",
    )

    @model_validator(mode="after")
    def validate_ranges(self) -> Self:
        if (
            self.expected_price_min is not None
            and self.expected_price_max is not None
            and self.expected_price_min > self.expected_price_max
        ):
            raise ValueError("expected_price_min must not exceed expected_price_max")
        if (
            self.expected_return_min_pct is not None
            and self.expected_return_max_pct is not None
            and self.expected_return_min_pct > self.expected_return_max_pct
        ):
            raise ValueError("expected_return_min_pct must not exceed expected_return_max_pct")
        if self.assessment_type == "InsufficientData" and self.direction != "InsufficientData":
            raise ValueError("InsufficientData assessment must use InsufficientData direction")
        return self


class ListingOutlook(models_ai.StrictAIModel):
    """Listing outlook across the initial trading periods."""

    ipo_day: ListingPeriodOutlook = Field(description="Outlook for the initial listing day.")
    first_week: ListingPeriodOutlook = Field(description="Outlook through the first week.")
    first_two_weeks: ListingPeriodOutlook = Field(description="Outlook through the first two weeks.")
    first_month: ListingPeriodOutlook = Field(description="Outlook through the first month.")


class ListingAnalysisBase(models_ai.StrictAIModel):
    """Core structured assessment of a new or recently completed listing."""

    symbol: models_types.NonEmptyString = Field(description="Canonical exchange-qualified listing symbol.")
    as_of: datetime = Field(description="Timestamp when the analysis was finalized.")
    listing_status: ListingStatus = Field(description="Whether the security is upcoming or already listed.")
    overall_data_quality: models_types.DataQuality = Field(
        description="Overall quality of evidence supporting the analysis."
    )
    executive_summary: ListingAnalysisSection = Field(description="Concise evidence-backed summary of the listing.")
    overall_stance: ListingStance = Field(description="Overall directional assessment of the listing.")
    overall_confidence: int = Field(
        ge=0,
        le=100,
        description="Confidence score for the overall assessment from zero through 100.",
    )
    offer: ListingOfferAnalysis = Field(description="Offer-structure assessment.")
    business: ListingBusinessAnalysis = Field(description="Business-model assessment.")
    financials: ListingFinancialAnalysis = Field(description="Financial assessment.")
    valuation: ListingValuationAnalysis = Field(description="Valuation assessment.")
    governance: ListingGovernanceAnalysis = Field(description="Governance assessment.")
    risks_and_catalysts: ListingRiskCatalystAnalysis = Field(description="Material risks and catalysts.")
    outlook: ListingOutlook = Field(description="Outlook across initial trading periods.")

    def referenced_source_ids(self) -> set[str]:
        return ai_reference_utils.collect_reference_ids(self)


class ListingAnalysis(ListingAnalysisBase):
    """Final listing analysis with a validated source registry."""

    references: list[models_ai.ReferenceSource] = Field(
        min_length=1,
        description="Canonical sources cited throughout the listing analysis.",
    )

    @model_validator(mode="after")
    def validate_references(self) -> Self:
        ai_reference_utils.validate_reference_registry(self.references, self)
        return self


class ListingEvent(event.EventBase):
    """A new or recently completed exchange-listing event."""

    model_config = ConfigDict(extra="forbid")

    symbol: models_types.NonEmptyString = Field(
        description="Canonical exchange-qualified symbol assigned to the listing."
    )
    date: str = Field(description="Scheduled or actual listing date.")
    issue_price: float | None = Field(
        gt=0,
        description="Offer price per security, or null when unavailable.",
    )
    issue_type: str | None = Field(
        default=None,
        description="Type of security or offer being listed.",
    )
    sector: str | None = Field(default=None, description="Issuer sector, when available.")
    industry: str | None = Field(default=None, description="Issuer industry, when available.")
    principal_activities: str | None = Field(
        default=None,
        description="Summary of the issuer's principal business activities.",
    )
    currency: models_types.NonEmptyString = Field(description="Currency of issue price and capital raised.")
    capital_to_raise: float | None = Field(
        gt=0,
        description="Target capital raise, or null when unavailable.",
    )
    public_offer_close_date: str | None = Field(
        default=None,
        description="Public-offer closing date, when applicable.",
    )
    is_underwritten: bool | None = Field(
        default=None,
        description="Whether the offer is underwritten, or null when not disclosed.",
    )
    underwriters: list[str] = Field(
        default_factory=list,
        description="Organizations underwriting the offer.",
    )
    lead_managers: list[str] = Field(
        default_factory=list,
        description="Lead managers responsible for the offer.",
    )
    analysis_status: ListingAnalysisStatus = Field(
        default="NotStarted",
        description="Lifecycle state of AI analysis for the listing.",
    )
    analysis_error: str | None = Field(
        default=None,
        description="Analysis failure detail, or null when no failure occurred.",
    )
    analysis: ListingAnalysis | None = Field(
        default=None,
        description="Structured listing analysis, or null when not completed.",
    )
