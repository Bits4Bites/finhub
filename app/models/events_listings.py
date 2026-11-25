from __future__ import annotations

import datetime
import typing

import pydantic

from ..utils import ai_reference as ai_reference_utils
from . import ai as models_ai
from . import events_base
from . import portfolio as models_portfolio
from . import types as models_types

ListingStatus = typing.Literal["Upcoming", "Listed"]
ListingStance = typing.Literal["Bullish", "Neutral", "Bearish", "InsufficientData"]
ListingAnalysisStatus = typing.Literal["NotStarted", "Completed", "Failed", "Skipped"]
ListingOutlookAssessmentType = typing.Literal["Forecast", "Observed", "InsufficientData"]
ListingOutlookDirection = typing.Literal["Up", "Flat", "Down", "InsufficientData"]
ListingRiskSeverity = typing.Literal["Critical", "High", "Medium", "Low"]
ListingLikelihood = typing.Literal["High", "Medium", "Low"]
ListingHorizon = typing.Literal["IPO Day", "First Week", "First Two Weeks", "First Month", "Longer Term"]


class ListingEvidenceClaim(models_ai.StrictAIModel):
    """One factual claim used in a new-listing analysis."""

    text: models_types.NonEmptyString = pydantic.Field(description="Factual evidence statement.")
    reference_ids: list[models_types.NonEmptyString] = pydantic.Field(
        min_length=1,
        description="Identifiers of sources supporting the claim.",
    )


class ListingEvidenceSection(models_ai.StrictAIModel):
    """A group of sourced listing facts and known evidence gaps."""

    facts: list[ListingEvidenceClaim] = pydantic.Field(description="Sourced facts relevant to this analysis section.")
    data_gaps: list[str] = pydantic.Field(description="Missing, unavailable, or conflicting evidence for the section.")
    reference_ids: list[models_types.NonEmptyString] = pydantic.Field(
        min_length=1,
        description="Identifiers of all sources used by the section.",
    )


class ListingAnalysisSection(ListingEvidenceSection):
    """Common assessment content shared by listing-analysis sections."""

    summary: models_types.NonEmptyString = pydantic.Field(description="Concise conclusion for the analysis section.")
    data_quality: models_types.DataQuality = pydantic.Field(
        description="Quality of the evidence supporting the section."
    )
    assumptions: list[str] = pydantic.Field(description="Assumptions used when interpreting available evidence.")


class ListingOfferAnalysis(ListingAnalysisSection):
    """Assessment of the listing offer structure and capital raising."""

    issue_price_assessment: models_types.NonEmptyString = pydantic.Field(
        description="Assessment of the offered issue price."
    )
    capital_raise_assessment: models_types.NonEmptyString = pydantic.Field(
        description="Assessment of the amount and structure of capital raised."
    )
    underwriting_assessment: models_types.NonEmptyString = pydantic.Field(
        description="Assessment of underwriting support and execution risk."
    )
    use_of_funds: list[str] = pydantic.Field(description="Material stated uses of listing proceeds.")
    dilution_and_escrow: str | None = pydantic.Field(
        description="Assessment of dilution, escrow, and lock-up effects, when available."
    )


class ListingBusinessAnalysis(ListingAnalysisSection):
    """Assessment of the issuer's business model and competitive context."""

    business_model: models_types.NonEmptyString = pydantic.Field(
        description="Description and assessment of how the issuer creates value."
    )
    revenue_sources: list[str] = pydantic.Field(description="Material sources of issuer revenue.")
    competitive_position: models_types.NonEmptyString = pydantic.Field(
        description="Assessment of the issuer's competitive position."
    )
    sector_context: models_types.NonEmptyString = pydantic.Field(
        description="Relevant sector conditions affecting the issuer."
    )


class ListingFinancialAnalysis(ListingAnalysisSection):
    """Assessment of issuer financial performance and funding quality."""

    historical_performance: models_types.NonEmptyString = pydantic.Field(
        description="Assessment of available historical financial performance."
    )
    profitability_and_cash_flow: models_types.NonEmptyString = pydantic.Field(
        description="Assessment of profitability and cash-flow characteristics."
    )
    balance_sheet_and_funding: models_types.NonEmptyString = pydantic.Field(
        description="Assessment of balance-sheet strength and funding requirements."
    )
    forecast_quality: models_types.NonEmptyString = pydantic.Field(
        description="Assessment of management forecasts and their supporting evidence."
    )


class ListingValuationAnalysis(ListingAnalysisSection):
    """Assessment of listing valuation and sensitivity."""

    valuation_view: models_types.NonEmptyString = pydantic.Field(description="Overall view of the offer valuation.")
    implied_market_cap: float | None = pydantic.Field(
        description="Implied market capitalization at the issue price, when derivable."
    )
    peer_comparison: models_types.NonEmptyString = pydantic.Field(description="Comparison with relevant listed peers.")
    sensitivity: models_types.NonEmptyString = pydantic.Field(
        description="Key assumptions and variables to which valuation is sensitive."
    )


class ListingGovernanceAnalysis(ListingAnalysisSection):
    """Assessment of issuer leadership, ownership, and governance."""

    board_and_management: models_types.NonEmptyString = pydantic.Field(
        description="Assessment of board and management experience and suitability."
    )
    ownership_and_escrow: models_types.NonEmptyString = pydantic.Field(
        description="Assessment of post-listing ownership, escrow, and lock-up arrangements."
    )
    governance_concerns: list[str] = pydantic.Field(
        description="Material governance concerns identified from available evidence."
    )


class ListingDriver(models_ai.StrictAIModel):
    """Common evidence-linked driver affecting a new listing."""

    title: models_types.NonEmptyString = pydantic.Field(description="Short label for the driver.")
    description: models_types.NonEmptyString = pydantic.Field(
        description="Explanation of how the driver may affect the listing."
    )
    likelihood: ListingLikelihood = pydantic.Field(description="Estimated likelihood that the driver will materialize.")
    horizon: ListingHorizon = pydantic.Field(description="Period over which the driver is relevant.")
    reference_ids: list[models_types.NonEmptyString] = pydantic.Field(
        min_length=1,
        description="Identifiers of sources supporting the driver.",
    )


class ListingRisk(ListingDriver):
    """A material downside driver for a new listing."""

    severity: ListingRiskSeverity = pydantic.Field(description="Potential impact severity of the risk.")


class ListingCatalyst(ListingDriver):
    """A potential positive catalyst for a new listing."""


class ListingRiskCatalystAnalysis(ListingAnalysisSection):
    """Assessment of material listing risks and positive catalysts."""

    risks: list[ListingRisk] = pydantic.Field(description="Material downside risks for the listing.")
    catalysts: list[ListingCatalyst] = pydantic.Field(description="Potential positive catalysts for the listing.")


class ListingPeriodOutlook(models_ai.StrictAIModel):
    """Observed or forecast listing performance for a defined period.

    Each supplied lower price or return bound must not exceed its upper bound.
    Insufficient-data assessments use the matching direction.
    """

    assessment_type: ListingOutlookAssessmentType = pydantic.Field(
        description="Whether the outlook is observed, forecast, or unavailable."
    )
    period_end: datetime.date | None = pydantic.Field(
        description="End date of the assessment period, or null when unavailable."
    )
    direction: ListingOutlookDirection = pydantic.Field(
        description="Expected or observed price direction over the period."
    )
    expected_price_min: float | None = pydantic.Field(
        description="Lower expected or observed price bound, when available."
    )
    expected_price_max: float | None = pydantic.Field(
        description="Upper expected or observed price bound, when available."
    )
    expected_return_min_pct: float | None = pydantic.Field(
        description="Lower expected or observed percentage-return bound."
    )
    expected_return_max_pct: float | None = pydantic.Field(
        description="Upper expected or observed percentage-return bound."
    )
    confidence: int = pydantic.Field(
        ge=0,
        le=100,
        description="Confidence score for the outlook from zero through 100.",
    )
    rationale: models_types.NonEmptyString = pydantic.Field(
        description="Evidence-based explanation of the period outlook."
    )
    key_drivers: list[str] = pydantic.Field(description="Factors expected to drive the period outcome.")
    risk_factors: list[str] = pydantic.Field(description="Factors that could impair the period outcome.")
    assumptions: list[str] = pydantic.Field(description="Assumptions underlying the outlook.")
    data_gaps: list[str] = pydantic.Field(description="Missing or uncertain information affecting the outlook.")
    reference_ids: list[models_types.NonEmptyString] = pydantic.Field(
        min_length=1,
        description="Identifiers of sources supporting the outlook.",
    )

    @pydantic.model_validator(mode="after")
    def validate_ranges(self) -> typing.Self:
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

    ipo_day: ListingPeriodOutlook = pydantic.Field(description="Outlook for the initial listing day.")
    first_week: ListingPeriodOutlook = pydantic.Field(description="Outlook through the first week.")
    first_two_weeks: ListingPeriodOutlook = pydantic.Field(description="Outlook through the first two weeks.")
    first_month: ListingPeriodOutlook = pydantic.Field(description="Outlook through the first month.")


class ListingAnalysisBase(models_ai.StrictAIModel):
    """Core structured assessment of a new or recently completed listing."""

    symbol: models_types.NonEmptyString = pydantic.Field(
        description=(
            "Canonical exchange-qualified listing symbol; input is trimmed, "
            "uppercased, and exchange aliases are canonicalized."
        )
    )
    as_of: datetime.datetime = pydantic.Field(description="Timestamp when the analysis was finalized.")
    listing_status: ListingStatus = pydantic.Field(description="Whether the security is upcoming or already listed.")
    overall_data_quality: models_types.DataQuality = pydantic.Field(
        description="Overall quality of evidence supporting the analysis."
    )
    executive_summary: ListingAnalysisSection = pydantic.Field(
        description="Concise evidence-backed summary of the listing."
    )
    overall_stance: ListingStance = pydantic.Field(description="Overall directional assessment of the listing.")
    overall_confidence: int = pydantic.Field(
        ge=0,
        le=100,
        description="Confidence score for the overall assessment from zero through 100.",
    )
    offer: ListingOfferAnalysis = pydantic.Field(description="Offer-structure assessment.")
    business: ListingBusinessAnalysis = pydantic.Field(description="Business-model assessment.")
    financials: ListingFinancialAnalysis = pydantic.Field(description="Financial assessment.")
    valuation: ListingValuationAnalysis = pydantic.Field(description="Valuation assessment.")
    governance: ListingGovernanceAnalysis = pydantic.Field(description="Governance assessment.")
    risks_and_catalysts: ListingRiskCatalystAnalysis = pydantic.Field(description="Material risks and catalysts.")
    outlook: ListingOutlook = pydantic.Field(description="Outlook across initial trading periods.")

    @pydantic.field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: object) -> object:
        return models_portfolio.normalize_canonical_ticker(value)

    def referenced_source_ids(self) -> set[str]:
        """Return every source identifier cited by this analysis.

        Returns:
            The unique IDs found in nested ``reference_ids`` fields. The source
            registry itself is not counted as a citation.
        """
        return ai_reference_utils.collect_reference_ids(self)


class ListingAnalysis(ListingAnalysisBase):
    """Final listing analysis with a validated source registry."""

    references: list[models_ai.ReferenceSource] = pydantic.Field(
        min_length=1,
        description="Canonical sources cited throughout the listing analysis, in application-supplied order.",
    )

    @pydantic.model_validator(mode="after")
    def validate_references(self) -> typing.Self:
        ai_reference_utils.validate_reference_registry(self.references, self)
        return self


class ListingEvent(events_base.EventBase):
    """A new or recently completed exchange-listing event.

    Completed events contain matching structured analysis and no error. Failed
    events contain a nonblank error and no analysis. NotStarted and Skipped
    events contain neither analysis nor an error.
    """

    model_config = pydantic.ConfigDict(extra="forbid")

    symbol: models_types.NonEmptyString = pydantic.Field(
        description=(
            "Canonical exchange-qualified symbol assigned to the listing; input "
            "is trimmed, uppercased, and exchange aliases are canonicalized."
        )
    )
    issue_price: float | None = pydantic.Field(
        gt=0,
        description="Fixed offer price per security or the lower bound of a price range, or null when unavailable.",
    )
    issue_price_upper: float | None = pydantic.Field(
        default=None,
        gt=0,
        description="Upper bound of an issue-price range, or null for a fixed or unavailable price.",
    )
    issue_type: str | None = pydantic.Field(
        default=None,
        description="Type of security or offer being listed.",
    )
    sector: str | None = pydantic.Field(default=None, description="Issuer sector, when available.")
    industry: str | None = pydantic.Field(default=None, description="Issuer industry, when available.")
    principal_activities: str | None = pydantic.Field(
        default=None,
        description="Summary of the issuer's principal business activities.",
    )
    currency: models_types.CurrencyCode = pydantic.Field(
        description=("Three-letter currency of issue price and capital raised; input is trimmed and uppercased.")
    )
    capital_to_raise: int | None = pydantic.Field(
        gt=0,
        description="Target capital raise, or null when unavailable.",
    )
    public_offer_close_date: str | None = pydantic.Field(
        default=None,
        description="Public-offer closing date, when applicable.",
    )
    is_underwritten: bool | None = pydantic.Field(
        default=None,
        description="Whether the offer is underwritten, or null when not disclosed.",
    )
    underwriters: list[str] = pydantic.Field(
        default_factory=list,
        description="Organizations underwriting the offer.",
    )
    lead_managers: list[str] = pydantic.Field(
        default_factory=list,
        description="Lead managers responsible for the offer.",
    )
    analysis_status: ListingAnalysisStatus = pydantic.Field(
        default="NotStarted",
        description=(
            "Lifecycle state of AI analysis: Completed includes analysis, Failed "
            "includes a nonblank error, and NotStarted or Skipped includes neither."
        ),
    )
    analysis_error: str | None = pydantic.Field(
        default=None,
        description="Nonblank failure detail for Failed analysis, otherwise null.",
    )
    analysis: ListingAnalysis | None = pydantic.Field(
        default=None,
        description="Structured listing analysis for Completed status, otherwise null.",
    )

    @pydantic.field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: object) -> object:
        return models_portfolio.normalize_canonical_ticker(value)

    @pydantic.field_validator("analysis_error", mode="before")
    @classmethod
    def normalize_analysis_error(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        return normalized or None

    @pydantic.model_validator(mode="after")
    def validate_listing_event(self) -> typing.Self:
        if (
            self.issue_price is not None
            and self.issue_price_upper is not None
            and self.issue_price > self.issue_price_upper
        ):
            raise ValueError("issue_price must not exceed issue_price_upper")
        if self.analysis_status == "Completed":
            if self.analysis is None:
                raise ValueError("Completed listing analysis requires analysis")
            if self.analysis_error is not None:
                raise ValueError("Completed listing analysis cannot contain an error")
            if self.analysis.symbol != self.symbol:
                raise ValueError("listing analysis symbol must match the event symbol")
        elif self.analysis_status == "Failed":
            if self.analysis_error is None:
                raise ValueError("Failed listing analysis requires a nonblank error")
            if self.analysis is not None:
                raise ValueError("Failed listing analysis cannot contain analysis")
        elif self.analysis is not None or self.analysis_error is not None:
            raise ValueError("NotStarted and Skipped listing analysis cannot contain analysis or an error")
        return self
