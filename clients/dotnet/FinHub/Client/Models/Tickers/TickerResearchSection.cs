using System.Text.Json.Serialization;
using FinHub.Client.Models.AI;

namespace FinHub.Client.Models.Tickers;

public sealed record TickerResearchSection
{
    [JsonPropertyName("summary")]
    public required string Summary { get; init; }

    [JsonPropertyName("data_quality")]
    public required DataQuality DataQuality { get; init; }

    [JsonPropertyName("claims")]
    public required IReadOnlyList<EvidenceClaim> Claims { get; init; }

    [JsonPropertyName("data_gaps")]
    public required IReadOnlyList<string> DataGaps { get; init; }

    [JsonPropertyName("reference_ids")]
    public required IReadOnlyList<string> ReferenceIds { get; init; }
}
