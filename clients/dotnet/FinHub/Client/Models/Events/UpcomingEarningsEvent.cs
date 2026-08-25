using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Events;

public sealed record UpcomingEarningsEvent : EventBase
{
    [JsonPropertyName("report_period")]
    public string? ReportPeriod { get; init; }

    [JsonPropertyName("status")]
    public string? Status { get; init; }
}
