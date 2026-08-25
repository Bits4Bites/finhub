using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Events;

public abstract record EventBase
{
    [JsonPropertyName("symbol")]
    public required string Symbol { get; init; }

    [JsonPropertyName("exchange")]
    public string? Exchange { get; init; }

    [JsonPropertyName("company_name")]
    public string? CompanyName { get; init; }

    [JsonPropertyName("timestamp")]
    public long Timestamp { get; init; } = 0;

    [JsonPropertyName("date")]
    public virtual string? Date { get; init; }

    [JsonPropertyName("event_category")]
    public string? EventCategory { get; init; }

    [JsonPropertyName("source_name")]
    public string? SourceName { get; init; }

    [JsonPropertyName("link")]
    public string? Link { get; init; }
}
