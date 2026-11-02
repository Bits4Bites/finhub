using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Dividends;

public sealed record DividendStrategyAssessment
{
    [JsonPropertyName("strategy")]
    public required DividendStrategy Strategy { get; init; }

    [JsonPropertyName("eligibility")]
    public required DividendStrategyEligibility Eligibility { get; init; }

    [JsonPropertyName("ineligibility_reason")]
    public required string? IneligibilityReason { get; init; }

    [JsonPropertyName("success_probability")]
    public double? SuccessProbability { get; init; }

    [JsonPropertyName("expected_entry_price")]
    public required DividendNumericRange? ExpectedEntryPrice { get; init; }

    [JsonPropertyName("expected_exit_price")]
    public required DividendNumericRange? ExpectedExitPrice { get; init; }

    [JsonPropertyName("expected_profit_loss_per_share")]
    public required DividendNumericRange? ExpectedProfitLossPerShare { get; init; }

    [JsonPropertyName("break_even_price")]
    public required DividendNumericRange? BreakEvenPrice { get; init; }

    [JsonPropertyName("recovery_days")]
    public required DividendDayRange? RecoveryDays { get; init; }

    [JsonPropertyName("confidence")]
    public required int Confidence { get; init; }

    [JsonPropertyName("risk")]
    public required int Risk { get; init; }

    [JsonPropertyName("rationale")]
    public required string Rationale { get; init; }

    [JsonPropertyName("risk_factors")]
    public required IReadOnlyList<string> RiskFactors { get; init; }

    [JsonPropertyName("assumptions")]
    public required IReadOnlyList<string> Assumptions { get; init; }

    [JsonPropertyName("data_gaps")]
    public required IReadOnlyList<string> DataGaps { get; init; }

    [JsonPropertyName("reference_ids")]
    public required IReadOnlyList<string> ReferenceIds { get; init; }
}
