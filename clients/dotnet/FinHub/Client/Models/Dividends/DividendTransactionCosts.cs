using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Dividends;

public sealed record DividendTransactionCosts
{
    [JsonPropertyName("dividend_capture_per_share")]
    public double DividendCapturePerShare { get; init; } = 0.0;

    [JsonPropertyName("post_dividend_discount_per_share")]
    public double PostDividendDiscountPerShare { get; init; } = 0.0;
}
