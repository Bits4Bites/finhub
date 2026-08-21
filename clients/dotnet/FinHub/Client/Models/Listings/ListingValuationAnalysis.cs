using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Listings;

public sealed record ListingValuationAnalysis : ListingAnalysisSection
{
    [JsonPropertyName("valuation_view")]
    public required string ValuationView { get; init; }

    [JsonPropertyName("implied_market_cap")]
    public required double? ImpliedMarketCap { get; init; }

    [JsonPropertyName("peer_comparison")]
    public required string PeerComparison { get; init; }

    [JsonPropertyName("sensitivity")]
    public required string Sensitivity { get; init; }
}
