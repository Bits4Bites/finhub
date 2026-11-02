using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Tickers;

public sealed record TickerResearch
{
    [JsonPropertyName("as_of")]
    public required DateTimeOffset AsOf { get; init; }

    [JsonPropertyName("business_profile")]
    public required TickerResearchSection BusinessProfile { get; init; }

    [JsonPropertyName("financial_performance")]
    public required TickerResearchSection FinancialPerformance { get; init; }

    [JsonPropertyName("valuation")]
    public required TickerResearchSection Valuation { get; init; }

    [JsonPropertyName("recent_developments")]
    public required TickerResearchSection RecentDevelopments { get; init; }

    [JsonPropertyName("catalysts")]
    public required TickerResearchSection Catalysts { get; init; }

    [JsonPropertyName("risks")]
    public required TickerResearchSection Risks { get; init; }

    [JsonPropertyName("market_consensus")]
    public required TickerResearchSection MarketConsensus { get; init; }

    [JsonPropertyName("asset_specific")]
    public required TickerResearchSection AssetSpecific { get; init; }

    [JsonPropertyName("data_gaps")]
    public required IReadOnlyList<string> DataGaps { get; init; }
}
