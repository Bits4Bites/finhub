using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Markets;

public sealed record MarketIndexConstituent
{
    [JsonPropertyName("symbol")]
    public required string Symbol { get; init; }

    [JsonPropertyName("company")]
    public required string Company { get; init; }

    [JsonPropertyName("sector")]
    public string? Sector { get; init; }

    [JsonPropertyName("market_cap")]
    public long? MarketCap { get; init; }
}
