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
    public double Open { get; init; } = 0.0;

    [JsonPropertyName("high")]
    public double High { get; init; } = 0.0;

    [JsonPropertyName("low")]
    public double Low { get; init; } = 0.0;

    [JsonPropertyName("close")]
    public double Close { get; init; } = 0.0;

    [JsonPropertyName("volume")]
    public long Volume { get; init; } = 0;

    [JsonPropertyName("dividends")]
    public double? Dividends { get; init; }

    [JsonPropertyName("rsi14")]
    public double? Rsi14 { get; init; }

    [JsonPropertyName("dvt")]
    public double? Dvt { get; init; }
}
