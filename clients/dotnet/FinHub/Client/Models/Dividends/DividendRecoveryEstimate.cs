using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Dividends;

public sealed record DividendRecoveryEstimate
{
    [JsonPropertyName("target_price")]
    public required DividendNumericRange TargetPrice { get; init; }

    [JsonPropertyName("success_probability")]
    public required double SuccessProbability { get; init; }

    [JsonPropertyName("days")]
    public DividendDayRange? Days { get; init; }

    [JsonPropertyName("estimated_date_min")]
    public DateOnly? EstimatedDateMin { get; init; }

    [JsonPropertyName("estimated_date_max")]
    public DateOnly? EstimatedDateMax { get; init; }
}
