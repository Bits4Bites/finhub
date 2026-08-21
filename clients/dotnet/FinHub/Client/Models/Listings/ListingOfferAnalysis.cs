using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Listings;

public sealed record ListingOfferAnalysis : ListingAnalysisSection
{
    [JsonPropertyName("issue_price_assessment")]
    public required string IssuePriceAssessment { get; init; }

    [JsonPropertyName("capital_raise_assessment")]
    public required string CapitalRaiseAssessment { get; init; }

    [JsonPropertyName("underwriting_assessment")]
    public required string UnderwritingAssessment { get; init; }

    [JsonPropertyName("use_of_funds")]
    public required IReadOnlyList<string> UseOfFunds { get; init; }

    [JsonPropertyName("dilution_and_escrow")]
    public required string? DilutionAndEscrow { get; init; }
}
