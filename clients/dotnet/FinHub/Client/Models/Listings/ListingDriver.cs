using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Listings;

public abstract record ListingDriver
{
    [JsonPropertyName("title")]
    public required string Title { get; init; }

    [JsonPropertyName("description")]
    public required string Description { get; init; }

    [JsonPropertyName("likelihood")]
    public required ListingLikelihood Likelihood { get; init; }

    [JsonPropertyName("horizon")]
    public required ListingHorizon Horizon { get; init; }

    [JsonPropertyName("reference_ids")]
    public required IReadOnlyList<string> ReferenceIds { get; init; }
}
