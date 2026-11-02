using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Tickers;

public sealed record TickerHoldingSnapshot
{
    [JsonPropertyName("num_shares")]
    public required decimal NumShares { get; init; }

    [JsonPropertyName("avg_price")]
    public required decimal AvgPrice { get; init; }

    [JsonPropertyName("currency")]
    public required string Currency { get; init; }

    [JsonPropertyName("market_price")]
    public required decimal MarketPrice { get; init; }

    [JsonPropertyName("cost_basis")]
    public required decimal CostBasis { get; init; }

    [JsonPropertyName("market_value")]
    public required decimal MarketValue { get; init; }

    [JsonPropertyName("unrealized_profit_loss")]
    public required decimal UnrealizedProfitLoss { get; init; }

    [JsonPropertyName("unrealized_return_pct")]
    public required decimal UnrealizedReturnPct { get; init; }

    [JsonPropertyName("break_even_price")]
    public required decimal BreakEvenPrice { get; init; }
}
