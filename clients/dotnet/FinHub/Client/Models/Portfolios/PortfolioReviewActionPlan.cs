using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Portfolios;

public sealed record PortfolioReviewActionPlan
{
    [JsonPropertyName("plan_type")]
    public required PortfolioReviewPlanType PlanType { get; init; }

    [JsonPropertyName("budget")]
    public required PortfolioBudget Budget { get; init; }

    [JsonPropertyName("cash_ledger")]
    public required PortfolioReviewCashLedger CashLedger { get; init; }

    [JsonPropertyName("summary")]
    public required string Summary { get; init; }

    [JsonPropertyName("actions")]
    public required IReadOnlyList<PortfolioReviewAction> Actions { get; init; }
}
