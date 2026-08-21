using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Dividends;

public sealed record DividendDropEstimate
{
    [JsonPropertyName("drop_amount")]
    public required DividendNumericRange DropAmount { get; init; }

    [JsonPropertyName("drop_percent")]
    public required DividendNumericRange DropPercent { get; init; }

    [JsonPropertyName("drop_to_dividend_ratio")]
    public required DividendNumericRange DropToDividendRatio { get; init; }

    [JsonPropertyName("estimated_price")]
    public required DividendNumericRange EstimatedPrice { get; init; }
}
