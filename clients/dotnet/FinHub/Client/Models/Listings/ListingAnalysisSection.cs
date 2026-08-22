using System.Text.Json.Serialization;
using FinHub.Client.Models.AI;

namespace FinHub.Client.Models.Listings;

public record ListingAnalysisSection : EvidenceSection
{
    [JsonPropertyName("summary")]
    public required string Summary { get; init; }

    [JsonPropertyName("data_quality")]
    public required DataQuality DataQuality { get; init; }

    [JsonPropertyName("assumptions")]
    public required IReadOnlyList<string> Assumptions { get; init; }
}
