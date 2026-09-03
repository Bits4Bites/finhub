using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Stocks;

public sealed record HistoryPoint
{
    [JsonPropertyName("timestamp")]
    public required long Timestamp { get; init; }

    [JsonPropertyName("timestamp_str")]
    public required string TimestampStr { get; init; }

    [JsonPropertyName("currency")]
    public string Currency { get; init; } = string.Empty;

    [JsonPropertyName("open")]
    public decimal Open { get; init; } = 0.0m;

    [JsonPropertyName("high")]
    public decimal High { get; init; } = 0.0m;

    [JsonPropertyName("low")]
    public decimal Low { get; init; } = 0.0m;

    [JsonPropertyName("close")]
    public decimal Close { get; init; } = 0.0m;

    [JsonPropertyName("volume")]
    public long Volume { get; init; } = 0;

    [JsonPropertyName("dividends")]
    public decimal? Dividends { get; init; }

    [JsonPropertyName("rsi14")]
    public decimal? Rsi14 { get; init; }

    [JsonPropertyName("dvt")]
    public decimal? Dvt { get; init; }
}
