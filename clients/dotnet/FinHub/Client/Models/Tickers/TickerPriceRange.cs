using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Tickers;

public sealed record TickerPriceRange
{
    [JsonPropertyName("minimum")]
    public required double Minimum { get; init; }

    [JsonPropertyName("maximum")]
    public required double Maximum { get; init; }

    [JsonPropertyName("currency")]
    public required string Currency { get; init; }
}
