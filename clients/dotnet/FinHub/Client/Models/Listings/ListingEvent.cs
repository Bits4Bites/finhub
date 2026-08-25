using System.Diagnostics.CodeAnalysis;
using System.Text.Json.Serialization;
using FinHub.Client.Models.Events;

namespace FinHub.Client.Models.Listings;

public sealed record ListingEvent : EventBase
{
    [JsonPropertyName("date")]
    [AllowNull]
    public required override string Date { get; init; }

    [JsonPropertyName("issue_price")]
    public required double? IssuePrice { get; init; }

    [JsonPropertyName("issue_type")]
    public string? IssueType { get; init; }

    [JsonPropertyName("sector")]
    public string? Sector { get; init; }

    [JsonPropertyName("industry")]
    public string? Industry { get; init; }

    [JsonPropertyName("principal_activities")]
    public string? PrincipalActivities { get; init; }

    [JsonPropertyName("currency")]
    public required string Currency { get; init; }

    [JsonPropertyName("capital_to_raise")]
    public required double? CapitalToRaise { get; init; }

    [JsonPropertyName("public_offer_close_date")]
    public string? PublicOfferCloseDate { get; init; }

    [JsonPropertyName("is_underwritten")]
    public bool? IsUnderwritten { get; init; }

    [JsonPropertyName("underwriters")]
    public IReadOnlyList<string> Underwriters { get; init; } = [];

    [JsonPropertyName("lead_managers")]
    public IReadOnlyList<string> LeadManagers { get; init; } = [];

    [JsonPropertyName("analysis_status")]
    public ListingAnalysisStatus AnalysisStatus { get; init; } = ListingAnalysisStatus.NotStarted;

    [JsonPropertyName("analysis_error")]
    public string? AnalysisError { get; init; }

    [JsonPropertyName("analysis")]
    public ListingAnalysis? Analysis { get; init; }
}
