using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Listings;

public record ListingAnalysisSection : ListingEvidenceSection
{
    [JsonPropertyName("summary")]
    public required string Summary { get; init; }

    [JsonPropertyName("data_quality")]
    public required ListingDataQuality DataQuality { get; init; }

    [JsonPropertyName("assumptions")]
    public required IReadOnlyList<string> Assumptions { get; init; }
}
