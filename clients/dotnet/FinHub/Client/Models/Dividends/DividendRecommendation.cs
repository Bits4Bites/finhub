using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Dividends;

public sealed record DividendRecommendation
{
    [JsonPropertyName("outcome")]
    public required DividendRecommendationOutcome Outcome { get; init; }

    [JsonPropertyName("probability_advantage")]
    public double? ProbabilityAdvantage { get; init; }

    [JsonPropertyName("rationale")]
    public required string Rationale { get; init; }

    [JsonPropertyName("reference_ids")]
    public required IReadOnlyList<string> ReferenceIds { get; init; }
}
