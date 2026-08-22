using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Portfolios;

public sealed record PortfolioVerifiedHolding
{
    [JsonPropertyName("ticker")]
    public required string Ticker { get; init; }

    [JsonPropertyName("company_name")]
    public string? CompanyName { get; init; }

    [JsonPropertyName("exchange")]
    public required string Exchange { get; init; }

    [JsonPropertyName("currency")]
    public required string Currency { get; init; }

    [JsonPropertyName("num_shares")]
    public required double NumShares { get; init; }

    [JsonPropertyName("avg_price")]
    public required double AvgPrice { get; init; }

    [JsonPropertyName("market_price")]
    public required double MarketPrice { get; init; }

    [JsonPropertyName("price_source")]
    public required PortfolioPriceSource PriceSource { get; init; }

    [JsonPropertyName("market_value")]
    public required double MarketValue { get; init; }

    [JsonPropertyName("current_allocation")]
    public required double CurrentAllocation { get; init; }

    [JsonPropertyName("target_allocation")]
    public double? TargetAllocation { get; init; }

    [JsonPropertyName("allocation_drift")]
    public double? AllocationDrift { get; init; }

    [JsonPropertyName("unrealized_profit_loss")]
    public double? UnrealizedProfitLoss { get; init; }

    [JsonPropertyName("tags")]
    public string? Tags { get; init; }
}
