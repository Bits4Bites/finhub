using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Listings;

public sealed record ListingRisk : ListingDriver
{
    [JsonPropertyName("severity")]
    public required ListingRiskSeverity Severity { get; init; }
}
