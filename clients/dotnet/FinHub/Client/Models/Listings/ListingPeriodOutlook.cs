using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Listings;

public sealed record ListingPeriodOutlook
{
    [JsonPropertyName("assessment_type")]
    public required ListingOutlookAssessmentType AssessmentType { get; init; }

    [JsonPropertyName("period_end")]
    public required DateOnly? PeriodEnd { get; init; }

    [JsonPropertyName("direction")]
    public required ListingOutlookDirection Direction { get; init; }

    [JsonPropertyName("expected_price_min")]
    public required double? ExpectedPriceMin { get; init; }

    [JsonPropertyName("expected_price_max")]
    public required double? ExpectedPriceMax { get; init; }

    [JsonPropertyName("expected_return_min_pct")]
    public required double? ExpectedReturnMinPct { get; init; }

    [JsonPropertyName("expected_return_max_pct")]
    public required double? ExpectedReturnMaxPct { get; init; }

    [JsonPropertyName("confidence")]
    public required int Confidence { get; init; }

    [JsonPropertyName("rationale")]
    public required string Rationale { get; init; }

    [JsonPropertyName("key_drivers")]
    public required IReadOnlyList<string> KeyDrivers { get; init; }

    [JsonPropertyName("risk_factors")]
    public required IReadOnlyList<string> RiskFactors { get; init; }

    [JsonPropertyName("assumptions")]
    public required IReadOnlyList<string> Assumptions { get; init; }

    [JsonPropertyName("data_gaps")]
    public required IReadOnlyList<string> DataGaps { get; init; }

    [JsonPropertyName("reference_ids")]
    public required IReadOnlyList<string> ReferenceIds { get; init; }
}
