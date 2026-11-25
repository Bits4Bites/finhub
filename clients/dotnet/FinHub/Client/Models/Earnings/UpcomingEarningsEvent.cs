using System.Text.Json.Serialization;
using FinHub.Client.Models.Events;

namespace FinHub.Client.Models.Earnings;

public sealed record UpcomingEarningsEvent : EventBase
{
    [JsonPropertyName("report_period")]
    public string? ReportPeriod { get; init; }

    [JsonPropertyName("status")]
    public string? Status { get; init; }

    [JsonPropertyName("market_cap")]
    public long MarketCap { get; init; }

    [JsonPropertyName("eps")]
    public decimal Eps { get; init; } = 0.0m;

    [JsonPropertyName("eps_forecast")]
    public decimal EpsForecast { get; init; } = 0.0m;

    [JsonPropertyName("revenue")]
    public long Revenue { get; init; }

    [JsonPropertyName("revenue_forecast")]
    public long RevenueForecast { get; init; }

    [JsonPropertyName("currency")]
    public string Currency { get; init; } = string.Empty;
}
