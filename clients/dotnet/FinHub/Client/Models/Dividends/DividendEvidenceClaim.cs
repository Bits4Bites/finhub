using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Dividends;

public sealed record DividendEvidenceClaim
{
    [JsonPropertyName("text")]
    public required string Text { get; init; }

    [JsonPropertyName("reference_ids")]
    public required IReadOnlyList<string> ReferenceIds { get; init; }
}
