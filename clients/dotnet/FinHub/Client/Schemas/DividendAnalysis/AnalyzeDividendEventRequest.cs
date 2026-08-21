using System.Text.Json.Serialization;
using FinHub.Client.Models.Dividends;

namespace FinHub.Client.Schemas.DividendAnalysis;

public sealed record AnalyzeDividendEventRequest
{
    [JsonPropertyName("symbol")]
    public required string Symbol { get; init; }

    [JsonPropertyName("ex_date")]
    public required DateOnly ExDate { get; init; }

    [JsonPropertyName("dividend_amount")]
    public required double DividendAmount { get; init; }

    [JsonPropertyName("transaction_costs")]
    public DividendTransactionCosts TransactionCosts { get; init; } = new();

    [JsonPropertyName("holding_period_days")]
    public int HoldingPeriodDays { get; init; } = 28;
}
