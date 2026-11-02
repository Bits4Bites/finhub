using System.Text.Json.Serialization;
using FinHub.Client.Models.AI;

namespace FinHub.Client.Models.Portfolios;

public sealed record PortfolioConstruction : IPortfolioAnalysisResult
{
    [JsonPropertyName("result_type")]
    public string ResultType { get; init; } = "PortfolioConstruction";

    [JsonPropertyName("as_of")]
    public required DateTimeOffset AsOf { get; init; }

    [JsonPropertyName("construction_status")]
    public required PortfolioConstructionStatus ConstructionStatus { get; init; }

    [JsonPropertyName("construction_mode")]
    public required PortfolioConstructionMode ConstructionMode { get; init; }

    [JsonPropertyName("country")]
    public required string Country { get; init; }

    [JsonPropertyName("investor_theme")]
    public required string InvestorTheme { get; init; }

    [JsonPropertyName("summary")]
    public required string Summary { get; init; }

    [JsonPropertyName("verified_seed_holdings")]
    public required IReadOnlyList<PortfolioVerifiedHolding> VerifiedSeedHoldings { get; init; }

    [JsonPropertyName("target_portfolio")]
    public required IReadOnlyList<PortfolioTargetPosition> TargetPortfolio { get; init; }

    [JsonPropertyName("action_plan")]
    public required PortfolioActionPlan? ActionPlan { get; init; }

    [JsonPropertyName("overall_data_quality")]
    public required DataQuality OverallDataQuality { get; init; }

    [JsonPropertyName("data_gaps")]
    public required IReadOnlyList<string> DataGaps { get; init; }

    [JsonPropertyName("validation_warnings")]
    public required IReadOnlyList<string> ValidationWarnings { get; init; }

    [JsonPropertyName("references")]
    public required IReadOnlyList<ReferenceSource> References { get; init; }
}
