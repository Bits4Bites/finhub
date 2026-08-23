using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Portfolios;

public sealed record PortfolioActionStep
{
    [JsonPropertyName("priority")]
    public required int Priority { get; init; }

    [JsonPropertyName("action")]
    public required PortfolioActionType Action { get; init; }

    [JsonPropertyName("ticker")]
    public required string Ticker { get; init; }

    [JsonPropertyName("company_name")]
    public string? CompanyName { get; init; }

    [JsonPropertyName("instruction")]
    public required string Instruction { get; init; }

    [JsonPropertyName("quantity")]
    public int? Quantity { get; init; }

    [JsonPropertyName("market_price")]
    public double? MarketPrice { get; init; }

    [JsonPropertyName("estimated_amount")]
    public double? EstimatedAmount { get; init; }

    [JsonPropertyName("target_allocation")]
    public double? TargetAllocation { get; init; }

    [JsonPropertyName("reasoning")]
    public required string Reasoning { get; init; }

    [JsonPropertyName("reference_ids")]
    public required IReadOnlyList<string> ReferenceIds { get; init; }
}
