using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Dividends;

public sealed record DividendNumericRange
{
    [JsonPropertyName("minimum")]
    public required double Minimum { get; init; }

    [JsonPropertyName("maximum")]
    public required double Maximum { get; init; }
}
