using System.Text.Json.Serialization;

namespace FinHub.Client.Models.AI;

public sealed record EvidenceClaim
{
    [JsonPropertyName("text")]
    public required string Text { get; init; }

    [JsonPropertyName("reference_ids")]
    public required IReadOnlyList<string> ReferenceIds { get; init; }
}
