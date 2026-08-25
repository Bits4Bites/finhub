using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Stocks;

public sealed record StockHistory
{
    [JsonPropertyName("recent_high_price")]
    public double RecentHighPrice { get; init; } = 0.0;

    [JsonPropertyName("pull_pack_percent")]
    public double PullPackPercent { get; init; } = 0.0;

    [JsonPropertyName("current_volume")]
    public long CurrentVolume { get; init; } = 0;

    [JsonPropertyName("yesterday_volume")]
    public long YesterdayVolume { get; init; } = 0;

    [JsonPropertyName("average_volume_30d")]
    public long AverageVolume30D { get; init; } = 0;

    [JsonPropertyName("ma10")]
    public double Ma10 { get; init; } = 0.0;

    [JsonPropertyName("ma20")]
    public double Ma20 { get; init; } = 0.0;

    [JsonPropertyName("ma50")]
    public double Ma50 { get; init; } = 0.0;

    [JsonPropertyName("ma100")]
    public double Ma100 { get; init; } = 0.0;

    [JsonPropertyName("ma200")]
    public double Ma200 { get; init; } = 0.0;

    [JsonPropertyName("rsi14")]
    public double Rsi14 { get; init; } = 0.0;

    [JsonPropertyName("history_90d")]
    public IReadOnlyList<HistoryPoint> History90D { get; init; } = [];
}
