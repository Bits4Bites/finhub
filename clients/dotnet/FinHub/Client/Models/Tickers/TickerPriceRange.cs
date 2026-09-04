using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Tickers;

public sealed record TickerPriceRange
{
    [JsonPropertyName("minimum")]
    public required decimal Minimum { get; init; }

    [JsonPropertyName("maximum")]
    public required decimal Maximum { get; init; }

    [JsonPropertyName("currency")]
    public required string Currency { get; init; }
}
