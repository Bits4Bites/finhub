using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Portfolios;

public sealed record PortfolioHolding
{
    [JsonPropertyName("ticker")]
    public required string Ticker { get; init; }

    [JsonPropertyName("num_shares")]
    public double NumShares { get; init; } = 0.0;

    [JsonPropertyName("avg_price")]
    public double AvgPrice { get; init; } = 0.0;

    [JsonPropertyName("market_price")]
    public double? MarketPrice { get; init; }

    [JsonPropertyName("target_allocation")]
    public double? TargetAllocation { get; init; }

    [JsonPropertyName("tags")]
    public string? Tags { get; init; }
}
