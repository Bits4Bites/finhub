using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Portfolios;

public sealed record PortfolioActionPlan
{
    [JsonPropertyName("budget")]
    public required PortfolioBudget Budget { get; init; }

    [JsonPropertyName("summary")]
    public required string Summary { get; init; }

    [JsonPropertyName("budget_utilized")]
    public double? BudgetUtilized { get; init; }

    [JsonPropertyName("unallocated_amount")]
    public double? UnallocatedAmount { get; init; }

    [JsonPropertyName("steps")]
    public required IReadOnlyList<PortfolioActionStep> Steps { get; init; }
}
