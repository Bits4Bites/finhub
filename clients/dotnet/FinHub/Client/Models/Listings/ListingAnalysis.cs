using System.Text.Json.Serialization;
using FinHub.Client.Models.AI;

namespace FinHub.Client.Models.Listings;

public sealed record ListingAnalysis
{
    [JsonPropertyName("symbol")]
    public required string Symbol { get; init; }

    [JsonPropertyName("as_of")]
    public required DateTimeOffset AsOf { get; init; }

    [JsonPropertyName("listing_status")]
    public required ListingStatus ListingStatus { get; init; }

    [JsonPropertyName("overall_data_quality")]
    public required DataQuality OverallDataQuality { get; init; }

    [JsonPropertyName("executive_summary")]
    public required ListingAnalysisSection ExecutiveSummary { get; init; }

    [JsonPropertyName("overall_stance")]
    public required ListingStance OverallStance { get; init; }

    [JsonPropertyName("overall_confidence")]
    public required int OverallConfidence { get; init; }

    [JsonPropertyName("offer")]
    public required ListingOfferAnalysis Offer { get; init; }

    [JsonPropertyName("business")]
    public required ListingBusinessAnalysis Business { get; init; }

    [JsonPropertyName("financials")]
    public required ListingFinancialAnalysis Financials { get; init; }

    [JsonPropertyName("valuation")]
    public required ListingValuationAnalysis Valuation { get; init; }

    [JsonPropertyName("governance")]
    public required ListingGovernanceAnalysis Governance { get; init; }

    [JsonPropertyName("risks_and_catalysts")]
    public required ListingRiskCatalystAnalysis RisksAndCatalysts { get; init; }

    [JsonPropertyName("outlook")]
    public required ListingOutlook Outlook { get; init; }

    [JsonPropertyName("references")]
    public required IReadOnlyList<ReferenceSource> References { get; init; }
}
