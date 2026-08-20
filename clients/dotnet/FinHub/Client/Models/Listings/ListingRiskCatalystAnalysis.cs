using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Listings;

public sealed record ListingRiskCatalystAnalysis : ListingAnalysisSection
{
    [JsonPropertyName("risks")]
    public required IReadOnlyList<ListingRisk> Risks { get; init; }

    [JsonPropertyName("catalysts")]
    public required IReadOnlyList<ListingCatalyst> Catalysts { get; init; }
}
