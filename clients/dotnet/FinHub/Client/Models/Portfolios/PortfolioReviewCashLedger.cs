using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Portfolios;

public sealed record PortfolioReviewCashLedger
{
    [JsonPropertyName("new_money_budget")]
    public required double NewMoneyBudget { get; init; }

    [JsonPropertyName("estimated_sale_proceeds")]
    public required double EstimatedSaleProceeds { get; init; }

    [JsonPropertyName("purchase_spend")]
    public required double PurchaseSpend { get; init; }

    [JsonPropertyName("unallocated_cash")]
    public required double UnallocatedCash { get; init; }
}
