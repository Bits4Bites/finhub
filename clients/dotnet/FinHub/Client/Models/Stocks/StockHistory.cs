using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Stocks;

public sealed record StockHistory
{
    [JsonPropertyName("recent_high_price")]
    public decimal RecentHighPrice { get; init; } = 0.0m;

    [JsonPropertyName("pull_pack_percent")]
    public decimal PullPackPercent { get; init; } = 0.0m;

    [JsonPropertyName("current_volume")]
    public long CurrentVolume { get; init; } = 0;

    [JsonPropertyName("yesterday_volume")]
    public long YesterdayVolume { get; init; } = 0;

    [JsonPropertyName("average_volume_30d")]
    public long AverageVolume30D { get; init; } = 0;

    [JsonPropertyName("ma10")]
    public decimal Ma10 { get; init; } = 0.0m;

    [JsonPropertyName("ma20")]
    public decimal Ma20 { get; init; } = 0.0m;

    [JsonPropertyName("ma50")]
    public decimal Ma50 { get; init; } = 0.0m;

    [JsonPropertyName("ma100")]
    public decimal Ma100 { get; init; } = 0.0m;

    [JsonPropertyName("ma200")]
    public decimal Ma200 { get; init; } = 0.0m;

    [JsonPropertyName("rsi14")]
    public decimal Rsi14 { get; init; } = 0.0m;

    [JsonPropertyName("history_90d")]
    public IReadOnlyList<HistoryPoint> History90D { get; init; } = [];
}
