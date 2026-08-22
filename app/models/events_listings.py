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
    text: models_types.NonEmptyString
    reference_ids: list[models_types.NonEmptyString] = Field(min_length=1)


class ListingEvidenceSection(models_ai.StrictAIModel):
    facts: list[ListingEvidenceClaim]
    data_gaps: list[str]
    reference_ids: list[models_types.NonEmptyString] = Field(min_length=1)


class ListingAnalysisSection(ListingEvidenceSection):
    summary: models_types.NonEmptyString
    data_quality: models_types.DataQuality
    assumptions: list[str]


class ListingOfferAnalysis(ListingAnalysisSection):
    issue_price_assessment: models_types.NonEmptyString
    capital_raise_assessment: models_types.NonEmptyString
    underwriting_assessment: models_types.NonEmptyString
    use_of_funds: list[str]
    dilution_and_escrow: str | None


class ListingBusinessAnalysis(ListingAnalysisSection):
    business_model: models_types.NonEmptyString
    revenue_sources: list[str]
    competitive_position: models_types.NonEmptyString
    sector_context: models_types.NonEmptyString


class ListingFinancialAnalysis(ListingAnalysisSection):
    historical_performance: models_types.NonEmptyString
    profitability_and_cash_flow: models_types.NonEmptyString
    balance_sheet_and_funding: models_types.NonEmptyString
    forecast_quality: models_types.NonEmptyString


class ListingValuationAnalysis(ListingAnalysisSection):
    valuation_view: models_types.NonEmptyString
    implied_market_cap: float | None
    peer_comparison: models_types.NonEmptyString
    sensitivity: models_types.NonEmptyString


class ListingGovernanceAnalysis(ListingAnalysisSection):
    board_and_management: models_types.NonEmptyString
    ownership_and_escrow: models_types.NonEmptyString
    governance_concerns: list[str]


class ListingDriver(models_ai.StrictAIModel):
    title: models_types.NonEmptyString
    description: models_types.NonEmptyString
    likelihood: ListingLikelihood
    horizon: ListingHorizon
    reference_ids: list[models_types.NonEmptyString] = Field(min_length=1)


class ListingRisk(ListingDriver):
    severity: ListingRiskSeverity


class ListingCatalyst(ListingDriver):
    pass


class ListingRiskCatalystAnalysis(ListingAnalysisSection):
    risks: list[ListingRisk]
    catalysts: list[ListingCatalyst]


class ListingPeriodOutlook(models_ai.StrictAIModel):
    assessment_type: ListingOutlookAssessmentType
    period_end: date | None
    direction: ListingOutlookDirection
    expected_price_min: float | None
    expected_price_max: float | None
    expected_return_min_pct: float | None
    expected_return_max_pct: float | None
    confidence: int = Field(ge=0, le=100)
    rationale: models_types.NonEmptyString
    key_drivers: list[str]
    risk_factors: list[str]
    assumptions: list[str]
    data_gaps: list[str]
    reference_ids: list[models_types.NonEmptyString] = Field(min_length=1)

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
    ipo_day: ListingPeriodOutlook
    first_week: ListingPeriodOutlook
    first_two_weeks: ListingPeriodOutlook
    first_month: ListingPeriodOutlook


class ListingAnalysisBase(models_ai.StrictAIModel):
    symbol: models_types.NonEmptyString
    as_of: datetime
    listing_status: ListingStatus
    overall_data_quality: models_types.DataQuality
    executive_summary: ListingAnalysisSection
    overall_stance: ListingStance
    overall_confidence: int = Field(ge=0, le=100)
    offer: ListingOfferAnalysis
    business: ListingBusinessAnalysis
    financials: ListingFinancialAnalysis
    valuation: ListingValuationAnalysis
    governance: ListingGovernanceAnalysis
    risks_and_catalysts: ListingRiskCatalystAnalysis
    outlook: ListingOutlook

    def referenced_source_ids(self) -> set[str]:
        return ai_reference_utils.collect_reference_ids(self)


class ListingAnalysis(ListingAnalysisBase):
    references: list[models_ai.ReferenceSource] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_references(self) -> Self:
        ai_reference_utils.validate_reference_registry(self.references, self)
        return self


class ListingEvent(event.EventBase):
    model_config = ConfigDict(extra="forbid")

    symbol: models_types.NonEmptyString
    date: str
    issue_price: float | None = Field(gt=0)
    issue_type: str | None = None
    sector: str | None = None
    industry: str | None = None
    principal_activities: str | None = None
    currency: models_types.NonEmptyString
    capital_to_raise: float | None = Field(gt=0)
    public_offer_close_date: str | None = None
    is_underwritten: bool | None = None
    underwriters: list[str] = Field(default_factory=list)
    lead_managers: list[str] = Field(default_factory=list)
    analysis_status: ListingAnalysisStatus = "NotStarted"
    analysis_error: str | None = None
    analysis: ListingAnalysis | None = None
