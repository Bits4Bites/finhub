using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Stocks;

public abstract record SymbolBase
{
    [JsonPropertyName("symbol")]
    public required string Symbol { get; init; }

    [JsonPropertyName("normalized_symbol")]
    public string NormalizedSymbol { get; init; } = string.Empty;

    [JsonPropertyName("currency")]
    public required string Currency { get; init; }

    [JsonPropertyName("exchange")]
    public required string Exchange { get; init; }

    [JsonPropertyName("country")]
    public required string Country { get; init; }
}
