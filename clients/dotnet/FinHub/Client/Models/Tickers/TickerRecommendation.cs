using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Tickers;

public sealed record TickerRecommendation
{
    [JsonPropertyName("action")]
    public required TickerRecommendationAction Action { get; init; }

    [JsonPropertyName("scope")]
    public required TickerRecommendationScope Scope { get; init; }

    [JsonPropertyName("confidence")]
    public required int Confidence { get; init; }

    [JsonPropertyName("summary")]
    public required string Summary { get; init; }

    [JsonPropertyName("buy_range")]
    public required TickerPriceRange? BuyRange { get; init; }

    [JsonPropertyName("sell_range")]
    public required TickerPriceRange? SellRange { get; init; }

    [JsonPropertyName("reasoning")]
    public required IReadOnlyList<string> Reasoning { get; init; }

    [JsonPropertyName("key_conditions")]
    public required IReadOnlyList<string> KeyConditions { get; init; }

    [JsonPropertyName("reassessment_triggers")]
    public required IReadOnlyList<string> ReassessmentTriggers { get; init; }

    [JsonPropertyName("risk_warnings")]
    public required IReadOnlyList<string> RiskWarnings { get; init; }

    [JsonPropertyName("reference_ids")]
    public required IReadOnlyList<string> ReferenceIds { get; init; }
}
