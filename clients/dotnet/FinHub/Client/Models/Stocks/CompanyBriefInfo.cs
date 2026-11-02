using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Stocks;

public sealed record CompanyBriefInfo
{
    [JsonPropertyName("symbol")]
    public string Symbol { get; init; } = string.Empty;

    [JsonPropertyName("name")]
    public string Name { get; init; } = string.Empty;

    [JsonPropertyName("sector")]
    public string Sector { get; init; } = string.Empty;

    [JsonPropertyName("market_cap")]
    public long MarketCap { get; init; } = 0;
}
