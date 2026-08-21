using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Dividends;

public sealed record DividendEvidenceSection
{
    [JsonPropertyName("facts")]
    public required IReadOnlyList<DividendEvidenceClaim> Facts { get; init; }

    [JsonPropertyName("data_gaps")]
    public required IReadOnlyList<string> DataGaps { get; init; }

    [JsonPropertyName("reference_ids")]
    public required IReadOnlyList<string> ReferenceIds { get; init; }
}
