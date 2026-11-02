using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Portfolios;

public sealed record PortfolioBudget
{
    [JsonPropertyName("budget_type")]
    public required PortfolioBudgetType BudgetType { get; init; }

    [JsonPropertyName("is_inferred")]
    public required bool IsInferred { get; init; }

    [JsonPropertyName("amount")]
    public required double? Amount { get; init; }

    [JsonPropertyName("currency")]
    public required string? Currency { get; init; }

    [JsonPropertyName("frequency")]
    public required PortfolioBudgetFrequency? Frequency { get; init; }

    [JsonPropertyName("source_text")]
    public required string? SourceText { get; init; }
}
