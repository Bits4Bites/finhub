using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Portfolios;

public sealed record PortfolioHoldingReview
{
    [JsonPropertyName("ticker")]
    public required string Ticker { get; init; }

    [JsonPropertyName("company_name")]
    public string? CompanyName { get; init; }

    [JsonPropertyName("role")]
    public required string Role { get; init; }

    [JsonPropertyName("current_allocation")]
    public required double CurrentAllocation { get; init; }

    [JsonPropertyName("target_allocation")]
    public required double TargetAllocation { get; init; }

    [JsonPropertyName("thesis")]
    public required string Thesis { get; init; }

    [JsonPropertyName("strengths")]
    public required IReadOnlyList<string> Strengths { get; init; }

    [JsonPropertyName("risks")]
    public required IReadOnlyList<string> Risks { get; init; }

    [JsonPropertyName("recommendation")]
    public required PortfolioReviewHoldingRecommendation Recommendation { get; init; }

    [JsonPropertyName("exit_reason")]
    public PortfolioReviewExitReason? ExitReason { get; init; }

    [JsonPropertyName("confidence")]
    public required int Confidence { get; init; }

    [JsonPropertyName("data_gaps")]
    public required IReadOnlyList<string> DataGaps { get; init; }

    [JsonPropertyName("reference_ids")]
    public required IReadOnlyList<string> ReferenceIds { get; init; }
}
