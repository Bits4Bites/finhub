using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Listings;

public abstract record ListingEvidenceSection
{
    [JsonPropertyName("facts")]
    public required IReadOnlyList<ListingEvidenceClaim> Facts { get; init; }

    [JsonPropertyName("data_gaps")]
    public required IReadOnlyList<string> DataGaps { get; init; }

    [JsonPropertyName("reference_ids")]
    public required IReadOnlyList<string> ReferenceIds { get; init; }
}
