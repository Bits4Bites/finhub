using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Tickers;

public sealed record TickerMarketSnapshot
{
    [JsonPropertyName("as_of")]
    public required DateTimeOffset AsOf { get; init; }

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

    [JsonPropertyName("sector")]
    public string? Sector { get; init; }

    [JsonPropertyName("industry")]
    public string? Industry { get; init; }

    [JsonPropertyName("market_price")]
    public required decimal MarketPrice { get; init; }

    [JsonPropertyName("previous_close")]
    public decimal? PreviousClose { get; init; }

    [JsonPropertyName("market_day_low")]
    public decimal? MarketDayLow { get; init; }

    [JsonPropertyName("market_day_high")]
    public decimal? MarketDayHigh { get; init; }

    [JsonPropertyName("fifty_two_week_low")]
    public decimal? FiftyTwoWeekLow { get; init; }

    [JsonPropertyName("fifty_two_week_high")]
    public decimal? FiftyTwoWeekHigh { get; init; }

    [JsonPropertyName("bid")]
    public decimal? Bid { get; init; }

    [JsonPropertyName("ask")]
    public decimal? Ask { get; init; }

    [JsonPropertyName("bid_ask_spread_pct")]
    public decimal? BidAskSpreadPct { get; init; }

    [JsonPropertyName("market_volume")]
    public long? MarketVolume { get; init; }

    [JsonPropertyName("market_cap")]
    public long? MarketCap { get; init; }

    [JsonPropertyName("beta")]
    public decimal? Beta { get; init; }

    [JsonPropertyName("analyst_recommendation")]
    public string? AnalystRecommendation { get; init; }

    [JsonPropertyName("analyst_target_low")]
    public decimal? AnalystTargetLow { get; init; }

    [JsonPropertyName("analyst_target_mean")]
    public decimal? AnalystTargetMean { get; init; }

    [JsonPropertyName("analyst_target_median")]
    public decimal? AnalystTargetMedian { get; init; }

    [JsonPropertyName("analyst_target_high")]
    public decimal? AnalystTargetHigh { get; init; }

    [JsonPropertyName("return_5d_pct")]
    public decimal? Return5DPct { get; init; }

    [JsonPropertyName("return_10d_pct")]
    public decimal? Return10DPct { get; init; }

    [JsonPropertyName("return_21d_pct")]
    public decimal? Return21DPct { get; init; }

    [JsonPropertyName("return_63d_pct")]
    public decimal? Return63DPct { get; init; }

    [JsonPropertyName("realized_volatility_20d_pct")]
    public decimal? RealizedVolatility20DPct { get; init; }

    [JsonPropertyName("realized_volatility_60d_pct")]
    public decimal? RealizedVolatility60DPct { get; init; }

    [JsonPropertyName("rsi14")]
    public decimal? Rsi14 { get; init; }

    [JsonPropertyName("ema_trend_pct")]
    public decimal? EmaTrendPct { get; init; }

    [JsonPropertyName("atr14")]
    public decimal? Atr14 { get; init; }

    [JsonPropertyName("benchmark_return_21d_pct")]
    public decimal? BenchmarkReturn21DPct { get; init; }

    [JsonPropertyName("peer_return_21d_pct")]
    public decimal? PeerReturn21DPct { get; init; }

    [JsonPropertyName("history_sample_count")]
    public required int HistorySampleCount { get; init; }

    [JsonPropertyName("data_gaps")]
    public required IReadOnlyList<string> DataGaps { get; init; }
}
