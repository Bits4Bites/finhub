using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Dividends;

public sealed record DividendTransactionCosts
{
    [JsonPropertyName("dividend_capture_per_share")]
    public decimal DividendCapturePerShare { get; init; } = 0.0m;

    [JsonPropertyName("post_dividend_discount_per_share")]
    public decimal PostDividendDiscountPerShare { get; init; } = 0.0m;
}
