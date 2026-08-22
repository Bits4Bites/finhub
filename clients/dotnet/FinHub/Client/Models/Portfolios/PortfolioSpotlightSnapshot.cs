using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Portfolios;

public sealed record PortfolioSpotlightSnapshot
{
    [JsonPropertyName("as_of")]
    public required DateTimeOffset AsOf { get; init; }

    [JsonPropertyName("country")]
    public required string Country { get; init; }

    [JsonPropertyName("currency")]
    public required string Currency { get; init; }

    [JsonPropertyName("total_market_value")]
    public required double TotalMarketValue { get; init; }

    [JsonPropertyName("holdings")]
    public required IReadOnlyList<PortfolioVerifiedHolding> Holdings { get; init; }

    [JsonPropertyName("data_gaps")]
    public required IReadOnlyList<string> DataGaps { get; init; }
}
