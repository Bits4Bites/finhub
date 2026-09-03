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

    [JsonPropertyName("date"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? TimestampStr { get; set; }

    [JsonIgnore]
    public DateTimeOffset Date => !string.IsNullOrEmpty(TimestampStr)
        ? DateTimeOffset.TryParse(TimestampStr, out var dt) ? dt.ToUniversalTime() : DateTimeOffset.FromUnixTimeSeconds(Timestamp).ToUniversalTime()
        : DateTimeOffset.FromUnixTimeSeconds(Timestamp).ToUniversalTime();

    [JsonPropertyName("event_category"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? EventCategory { get; init; }

    [JsonPropertyName("source_name"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? SourceName { get; init; }

    [JsonPropertyName("link"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? Link { get; init; }
}
