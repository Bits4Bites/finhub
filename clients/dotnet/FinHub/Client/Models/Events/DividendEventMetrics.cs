using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Events;

public sealed record DividendEventMetrics : EventBase
{
    [JsonPropertyName("price")]
    public double Price { get; init; } = 0.0;

    [JsonPropertyName("div_amount")]
    public double DividendAmount { get; init; } = 0.0;

    [JsonPropertyName("div_yield")]
    public double DividendYield { get; init; } = 0.0;

    [JsonPropertyName("num_samples")]
    public int NumSamples { get; init; } = 0;

    [JsonPropertyName("drop_price_min")]
    public double DropPriceMin { get; init; } = 0.0;

    [JsonPropertyName("drop_price_max")]
    public double DropPriceMax { get; init; } = 0.0;

    [JsonPropertyName("recovery_probability")]
    public double RecoveryProbability { get; init; } = 0.0;

    [JsonPropertyName("recovery_days_min")]
    public int RecoveryDaysMin { get; init; } = 0;

    [JsonPropertyName("recovery_days_max")]
    public int RecoveryDaysMax { get; init; } = 0;

    [JsonPropertyName("recovery_price_min")]
    public double RecoveryPriceMin { get; init; } = 0.0;

    [JsonPropertyName("recovery_price_max")]
    public double RecoveryPriceMax { get; init; } = 0.0;

    [JsonPropertyName("beta")]
    public double Beta { get; init; } = 0.0;

    [JsonPropertyName("rsi14")]
    public int Rsi14 { get; init; } = 0;

    [JsonPropertyName("avg_dvt_7d")]
    public long AverageDailyValueTraded7D { get; init; } = 0;

    [JsonPropertyName("std_dvt_7d")]
    public long DailyValueTradedStandardDeviation7D { get; init; } = 0;

    [JsonPropertyName("avg_volume_30d")]
    public long AverageVolume30D { get; init; } = 0;

    [JsonPropertyName("std_volume_30d")]
    public long VolumeStandardDeviation30D { get; init; } = 0;

    [JsonPropertyName("bid_ask_spread")]
    public double BidAskSpread { get; init; } = 0.0;

    [JsonPropertyName("trend_60d")]
    public double Trend60D { get; init; } = 0.0;

    [JsonPropertyName("market_trend_60d")]
    public double MarketTrend60D { get; init; } = 0.0;

    [JsonPropertyName("peer_trend_60d")]
    public double PeerTrend60D { get; init; } = 0.0;
}
