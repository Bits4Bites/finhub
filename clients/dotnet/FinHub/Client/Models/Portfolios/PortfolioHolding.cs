using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Portfolios;

public sealed record PortfolioHolding
{
    [JsonPropertyName("ticker")]
    public required string Ticker { get; init; }

    [JsonPropertyName("num_shares")]
    public decimal NumShares { get; init; } = 0.0m;

    [JsonPropertyName("avg_price")]
    public decimal AvgPrice { get; init; } = 0.0m;

    [JsonPropertyName("market_price")]
    public decimal? MarketPrice { get; init; }

    [JsonPropertyName("target_allocation")]
    public decimal? TargetAllocation { get; init; }

    [JsonPropertyName("tags")]
    public string? Tags { get; init; }
}
