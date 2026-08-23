using System.Text.Json.Serialization;
using FinHub.Client.Models.AI;

namespace FinHub.Client.Models.Portfolios;

public sealed record PortfolioReview : IPortfolioAnalysisResult
{
    [JsonPropertyName("result_type")]
    public string ResultType { get; init; } = "PortfolioReview";

    [JsonPropertyName("as_of")]
    public required DateTimeOffset AsOf { get; init; }

    [JsonPropertyName("review_status")]
    public required PortfolioReviewStatus ReviewStatus { get; init; }

    [JsonPropertyName("strategy")]
    public required PortfolioReviewStrategy Strategy { get; init; }

    [JsonPropertyName("country")]
    public required string Country { get; init; }

    [JsonPropertyName("investor_theme")]
    public required string InvestorTheme { get; init; }

    [JsonPropertyName("snapshot")]
    public required PortfolioReviewSnapshot Snapshot { get; init; }

    [JsonPropertyName("budget")]
    public required PortfolioBudget Budget { get; init; }

    [JsonPropertyName("summary")]
    public required string Summary { get; init; }

    [JsonPropertyName("strengths")]
    public required IReadOnlyList<PortfolioReviewStrength> Strengths { get; init; }

    [JsonPropertyName("risks")]
    public required IReadOnlyList<PortfolioReviewRisk> Risks { get; init; }

    [JsonPropertyName("holding_reviews")]
    public required IReadOnlyList<PortfolioHoldingReview> HoldingReviews { get; init; }

    [JsonPropertyName("target_portfolio")]
    public required IReadOnlyList<PortfolioReviewTargetPosition> TargetPortfolio { get; init; }

    [JsonPropertyName("target_turnover")]
    public required double TargetTurnover { get; init; }

    [JsonPropertyName("rebalance_requested")]
    public required bool RebalanceRequested { get; init; }

    [JsonPropertyName("rebalance_recommended")]
    public required PortfolioReviewRebalanceFlag RebalanceRecommended { get; init; }

    [JsonPropertyName("major_rebalance_reasons")]
    public required IReadOnlyList<string> MajorRebalanceReasons { get; init; }

    [JsonPropertyName("action_plan")]
    public required PortfolioReviewActionPlan? ActionPlan { get; init; }

    [JsonPropertyName("overall_data_quality")]
    public required DataQuality OverallDataQuality { get; init; }

    [JsonPropertyName("data_gaps")]
    public required IReadOnlyList<string> DataGaps { get; init; }

    [JsonPropertyName("validation_warnings")]
    public required IReadOnlyList<string> ValidationWarnings { get; init; }

    [JsonPropertyName("references")]
    public required IReadOnlyList<ReferenceSource> References { get; init; }
}
