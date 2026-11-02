using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Dividends;

public sealed record DividendHistoricalBaseline
{
    [JsonPropertyName("sample_count")]
    public required int SampleCount { get; init; }

    [JsonPropertyName("sample_quality")]
    public required DividendSampleQuality SampleQuality { get; init; }

    [JsonPropertyName("quality_flags")]
    public required IReadOnlyList<string> QualityFlags { get; init; }

    [JsonPropertyName("ex_date_open_drop")]
    public required DividendDropEstimate ExDateOpenDrop { get; init; }

    [JsonPropertyName("ex_date_close_drop")]
    public required DividendDropEstimate ExDateCloseDrop { get; init; }

    [JsonPropertyName("ex_date_intraday_low_drop")]
    public required DividendDropEstimate ExDateIntradayLowDrop { get; init; }

    [JsonPropertyName("post_ex_date_drawdown")]
    public required DividendDropEstimate PostExDateDrawdown { get; init; }

    [JsonPropertyName("pre_ex_close_recovery")]
    public required DividendRecoveryEstimate PreExCloseRecovery { get; init; }

    [JsonPropertyName("dividend_capture_break_even_recovery")]
    public required DividendRecoveryEstimate DividendCaptureBreakEvenRecovery { get; init; }

    [JsonPropertyName("post_dividend_discount_break_even_recovery")]
    public required DividendRecoveryEstimate PostDividendDiscountBreakEvenRecovery { get; init; }

    [JsonPropertyName("technical_context")]
    public required DividendTechnicalContext TechnicalContext { get; init; }
}
