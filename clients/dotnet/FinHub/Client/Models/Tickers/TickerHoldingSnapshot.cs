using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Tickers;

public sealed record TickerHoldingSnapshot
{
    [JsonPropertyName("num_shares")]
    public required double NumShares { get; init; }

    [JsonPropertyName("avg_price")]
    public required double AvgPrice { get; init; }

    [JsonPropertyName("currency")]
    public required string Currency { get; init; }

    [JsonPropertyName("market_price")]
    public required double MarketPrice { get; init; }

    [JsonPropertyName("cost_basis")]
    public required double CostBasis { get; init; }

    [JsonPropertyName("market_value")]
    public required double MarketValue { get; init; }

    [JsonPropertyName("unrealized_profit_loss")]
    public required double UnrealizedProfitLoss { get; init; }

    [JsonPropertyName("unrealized_return_pct")]
    public required double UnrealizedReturnPct { get; init; }

    [JsonPropertyName("break_even_price")]
    public required double BreakEvenPrice { get; init; }
}
