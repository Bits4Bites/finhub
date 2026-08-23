using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Portfolios;

public sealed record PortfolioBudget
{
    [JsonPropertyName("budget_type")]
    public required PortfolioBudgetType BudgetType { get; init; }

    [JsonPropertyName("amount")]
    public double? Amount { get; init; }

    [JsonPropertyName("currency")]
    public string? Currency { get; init; }

    [JsonPropertyName("frequency")]
    public PortfolioBudgetFrequency? Frequency { get; init; }

    [JsonPropertyName("source_text")]
    public string? SourceText { get; init; }
}
