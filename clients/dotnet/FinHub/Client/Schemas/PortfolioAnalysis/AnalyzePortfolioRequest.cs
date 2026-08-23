using System.Text.Json.Serialization;
using FinHub.Client.Models.Portfolios;

namespace FinHub.Client.Schemas.PortfolioAnalysis;

public sealed record AnalyzePortfolioRequest
{
    [JsonPropertyName("country")]
    public required string Country { get; init; }

    [JsonPropertyName("current_allocation")]
    public IReadOnlyList<PortfolioHolding> CurrentAllocation { get; init; } = [];

    [JsonPropertyName("investor_theme")]
    public required string InvestorTheme { get; init; }

    [JsonPropertyName("rebalance_plan")]
    public bool RebalancePlan { get; init; } = false;
}
