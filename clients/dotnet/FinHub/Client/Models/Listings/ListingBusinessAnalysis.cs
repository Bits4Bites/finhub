using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Listings;

public sealed record ListingBusinessAnalysis : ListingAnalysisSection
{
    [JsonPropertyName("business_model")]
    public required string BusinessModel { get; init; }

    [JsonPropertyName("revenue_sources")]
    public required IReadOnlyList<string> RevenueSources { get; init; }

    [JsonPropertyName("competitive_position")]
    public required string CompetitivePosition { get; init; }

    [JsonPropertyName("sector_context")]
    public required string SectorContext { get; init; }
}
