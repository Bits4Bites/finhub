using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Events;

public abstract record EventBase
{
    [JsonPropertyName("symbol")]
    public required string Symbol { get; init; }

    [JsonPropertyName("exchange"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? Exchange { get; init; }

    [JsonPropertyName("company_name"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? CompanyName { get; init; }

    [JsonPropertyName("timestamp")]
    public long Timestamp { get; init; } = 0;

    [JsonPropertyName("timestamp_str")]
    public required string TimestampStr { get; init; }

    [JsonIgnore]
    public virtual DateTimeOffset DateUTC => DateTimeOffset.TryParse(TimestampStr, out var dt)
        ? dt.ToUniversalTime()
        : DateTimeOffset.FromUnixTimeSeconds(Timestamp).ToUniversalTime();

    [JsonPropertyName("event_category"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? EventCategory { get; init; }

    [JsonPropertyName("source_name"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? SourceName { get; init; }

    [JsonPropertyName("link"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? Link { get; init; }
}
