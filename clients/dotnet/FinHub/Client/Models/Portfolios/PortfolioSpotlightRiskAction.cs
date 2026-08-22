using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Portfolios;

public sealed record PortfolioSpotlightRiskAction
{
    [JsonPropertyName("rank")]
    public required int Rank { get; init; }

    [JsonPropertyName("level")]
    public required PortfolioSpotlightRiskLevel Level { get; init; }

    [JsonPropertyName("action_timing")]
    public required PortfolioSpotlightActionTiming ActionTiming { get; init; }

    [JsonPropertyName("risk")]
    public required string Risk { get; init; }

    [JsonPropertyName("action")]
    public required string Action { get; init; }

    [JsonPropertyName("affected_tickers")]
    public required IReadOnlyList<string> AffectedTickers { get; init; }

    [JsonPropertyName("requires_rebalance")]
    public required bool RequiresRebalance { get; init; }

    [JsonPropertyName("confidence")]
    public required int Confidence { get; init; }

    [JsonPropertyName("data_gaps")]
    public required IReadOnlyList<string> DataGaps { get; init; }

    [JsonPropertyName("reference_ids")]
    public required IReadOnlyList<string> ReferenceIds { get; init; }
}
