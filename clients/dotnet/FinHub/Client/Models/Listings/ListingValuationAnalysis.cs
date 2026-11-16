using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Listings;

public sealed record ListingValuationAnalysis : ListingAnalysisSection
{
    [JsonPropertyName("valuation_view")]
    public string ValuationView { get; init; } = string.Empty;

    [JsonPropertyName("implied_market_cap")]
    public double? ImpliedMarketCap { get; init; }

    [JsonPropertyName("peer_comparison")]
    public string PeerComparison { get; init; } = string.Empty;

    [JsonPropertyName("sensitivity")]
    public string Sensitivity { get; init; } = string.Empty;
}
