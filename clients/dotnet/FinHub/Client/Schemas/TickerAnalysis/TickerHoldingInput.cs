using System.Text.Json.Serialization;

namespace FinHub.Client.Schemas.TickerAnalysis;

public sealed record TickerHoldingInput
{
    [JsonPropertyName("num_shares")]
    public required double NumShares { get; init; }

    [JsonPropertyName("avg_price")]
    public required double AvgPrice { get; init; }
}
