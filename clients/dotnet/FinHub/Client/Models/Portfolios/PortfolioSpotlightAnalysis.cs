using System.Text.Json.Serialization;
using FinHub.Client.Models.AI;

namespace FinHub.Client.Models.Portfolios;

public sealed record PortfolioSpotlightAnalysis
{
    [JsonPropertyName("as_of")]
    public required DateTimeOffset AsOf { get; init; }

    [JsonPropertyName("analysis_status")]
    public required PortfolioSpotlightAnalysisStatus AnalysisStatus { get; init; }

    [JsonPropertyName("portfolio_empty")]
    public required bool PortfolioEmpty { get; init; }

    [JsonPropertyName("overall_data_quality")]
    public required DataQuality OverallDataQuality { get; init; }

    [JsonPropertyName("snapshot")]
    public required PortfolioSpotlightSnapshot? Snapshot { get; init; }

    [JsonPropertyName("risks")]
    public required IReadOnlyList<PortfolioSpotlightRiskAction> Risks { get; init; }

    [JsonPropertyName("rebalance_recommended")]
    public required PortfolioSpotlightRebalanceFlag RebalanceRecommended { get; init; }

    [JsonPropertyName("data_gaps")]
    public required IReadOnlyList<string> DataGaps { get; init; }

    [JsonPropertyName("validation_warnings")]
    public required IReadOnlyList<string> ValidationWarnings { get; init; }

    [JsonPropertyName("references")]
    public required IReadOnlyList<ReferenceSource> References { get; init; }
}
