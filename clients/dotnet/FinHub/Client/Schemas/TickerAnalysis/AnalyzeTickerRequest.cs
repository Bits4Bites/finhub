using System.Text.Json.Serialization;

namespace FinHub.Client.Schemas.TickerAnalysis;

public sealed record AnalyzeTickerRequest
{
    [JsonPropertyName("symbol")]
    public required string Symbol { get; init; }

    [JsonPropertyName("intent")]
    public string? Intent { get; init; }

    [JsonPropertyName("current_holding")]
    public TickerHoldingInput? CurrentHolding { get; init; }
}
