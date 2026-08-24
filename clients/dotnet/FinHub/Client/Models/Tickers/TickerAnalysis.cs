using System.Text.Json.Serialization;
using FinHub.Client.Models.AI;

namespace FinHub.Client.Models.Tickers;

public sealed record TickerAnalysis
{
    [JsonPropertyName("as_of")]
    public required DateTimeOffset AsOf { get; init; }

    [JsonPropertyName("analysis_status")]
    public required TickerAnalysisStatus AnalysisStatus { get; init; }

    [JsonPropertyName("symbol")]
    public required string Symbol { get; init; }

    [JsonPropertyName("company_name")]
    public string? CompanyName { get; init; }

    [JsonPropertyName("asset_type")]
    public required TickerAssetType? AssetType { get; init; }

    [JsonPropertyName("exchange")]
    public required string Exchange { get; init; }

    [JsonPropertyName("country")]
    public required string Country { get; init; }

    [JsonPropertyName("currency")]
    public required string Currency { get; init; }

    [JsonPropertyName("market_snapshot")]
    public required TickerMarketSnapshot MarketSnapshot { get; init; }

    [JsonPropertyName("holding_snapshot")]
    public required TickerHoldingSnapshot? HoldingSnapshot { get; init; }

    [JsonPropertyName("research")]
    public required TickerResearch Research { get; init; }

    [JsonPropertyName("forecasts")]
    public required IReadOnlyList<TickerPriceForecast> Forecasts { get; init; }

    [JsonPropertyName("recommendation")]
    public required TickerRecommendation Recommendation { get; init; }

    [JsonPropertyName("overall_data_quality")]
    public required DataQuality OverallDataQuality { get; init; }

    [JsonPropertyName("data_gaps")]
    public required IReadOnlyList<string> DataGaps { get; init; }

    [JsonPropertyName("validation_warnings")]
    public required IReadOnlyList<string> ValidationWarnings { get; init; }

    [JsonPropertyName("references")]
    public required IReadOnlyList<ReferenceSource> References { get; init; }
}
