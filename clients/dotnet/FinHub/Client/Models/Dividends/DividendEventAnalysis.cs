using System.Text.Json.Serialization;
using FinHub.Client.Models.AI;

namespace FinHub.Client.Models.Dividends;

public sealed record DividendEventAnalysis
{
    [JsonPropertyName("as_of")]
    public required DateTimeOffset AsOf { get; init; }

    [JsonPropertyName("analysis_status")]
    public required DividendAnalysisStatus AnalysisStatus { get; init; }

    [JsonPropertyName("failure_reason")]
    public required string? FailureReason { get; init; }

    [JsonPropertyName("overall_data_quality")]
    public required DataQuality OverallDataQuality { get; init; }

    [JsonPropertyName("event")]
    public required DividendEventContext Event { get; init; }

    [JsonPropertyName("historical_baseline")]
    public required DividendHistoricalBaseline HistoricalBaseline { get; init; }

    [JsonPropertyName("research")]
    public required DividendResearch? Research { get; init; }

    [JsonPropertyName("evidence_adjusted_ex_date_close_drop")]
    public required DividendDropEstimate? EvidenceAdjustedExDateCloseDrop { get; init; }

    [JsonPropertyName("evidence_adjusted_pre_ex_close_recovery")]
    public required DividendRecoveryEstimate? EvidenceAdjustedPreExCloseRecovery { get; init; }

    [JsonPropertyName("evidence_adjusted_capture_break_even_recovery")]
    public required DividendRecoveryEstimate? EvidenceAdjustedCaptureBreakEvenRecovery { get; init; }

    [JsonPropertyName("evidence_adjusted_discount_break_even_recovery")]
    public required DividendRecoveryEstimate? EvidenceAdjustedDiscountBreakEvenRecovery { get; init; }

    [JsonPropertyName("dividend_capture")]
    public required DividendStrategyAssessment? DividendCapture { get; init; }

    [JsonPropertyName("post_dividend_discount")]
    public required DividendStrategyAssessment? PostDividendDiscount { get; init; }

    [JsonPropertyName("recommendation")]
    public required DividendRecommendation? Recommendation { get; init; }

    [JsonPropertyName("validation_warnings")]
    public required IReadOnlyList<string> ValidationWarnings { get; init; }

    [JsonPropertyName("references")]
    public required IReadOnlyList<ReferenceSource> References { get; init; }
}
