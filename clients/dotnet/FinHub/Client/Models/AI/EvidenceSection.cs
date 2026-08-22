using System.Text.Json.Serialization;

namespace FinHub.Client.Models.AI;

public record EvidenceSection
{
    [JsonPropertyName("facts")]
    public required IReadOnlyList<EvidenceClaim> Facts { get; init; }

    [JsonPropertyName("data_gaps")]
    public required IReadOnlyList<string> DataGaps { get; init; }

    [JsonPropertyName("reference_ids")]
    public required IReadOnlyList<string> ReferenceIds { get; init; }
}
