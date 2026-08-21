using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Dividends;

public sealed record DividendRecoveryEstimate
{
    [JsonPropertyName("target_price")]
    public required DividendNumericRange TargetPrice { get; init; }

    [JsonPropertyName("success_probability")]
    public required double SuccessProbability { get; init; }

    [JsonPropertyName("days")]
    public required DividendDayRange? Days { get; init; }

    [JsonPropertyName("estimated_date_min")]
    public required DateOnly? EstimatedDateMin { get; init; }

    [JsonPropertyName("estimated_date_max")]
    public required DateOnly? EstimatedDateMax { get; init; }
}
