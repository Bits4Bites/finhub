using System.Text.Json.Serialization;
using FinHub.Client.Models.Markets;

namespace FinHub.Client.Schemas.MarketIndex;

public sealed record GetMarketIndexResponse
{
    [JsonPropertyName("date")]
    public required DateOnly Date { get; init; }

    [JsonPropertyName("data")]
    public required IReadOnlyList<MarketIndexConstituent> Data { get; init; }
}
