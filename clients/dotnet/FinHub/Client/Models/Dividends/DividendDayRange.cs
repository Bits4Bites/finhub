using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Dividends;

public sealed record DividendDayRange
{
    [JsonPropertyName("minimum")]
    public required int Minimum { get; init; }

    [JsonPropertyName("maximum")]
    public required int Maximum { get; init; }
}
