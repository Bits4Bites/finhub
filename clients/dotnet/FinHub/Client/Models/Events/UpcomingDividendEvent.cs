using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Events;

public sealed record UpcomingDividendEvent : EventBase
{
    [JsonPropertyName("status")]
    public string Status { get; init; } = string.Empty;

    [JsonPropertyName("amount")]
    public decimal Amount { get; init; } = 0.0m;

    [JsonPropertyName("dividend_yield")]
    public decimal DividendYield { get; init; } = 0.0m;

    [JsonPropertyName("currency")]
    public string Currency { get; init; } = string.Empty;

    [JsonPropertyName("payment_date")]
    public required string? PaymentDate { get; init; }

    [JsonPropertyName("analysis")]
    public DividendEventMetrics? Analysis { get; init; }
}
