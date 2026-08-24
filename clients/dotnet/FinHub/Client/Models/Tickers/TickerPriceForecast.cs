using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Tickers;

public sealed record TickerPriceForecast
{
    [JsonPropertyName("horizon")]
    public required TickerForecastHorizon Horizon { get; init; }

    [JsonPropertyName("horizon_days")]
    public required int HorizonDays { get; init; }

    [JsonPropertyName("period_end")]
    public required DateOnly PeriodEnd { get; init; }

    [JsonPropertyName("assessment_status")]
    public required TickerForecastAssessmentStatus AssessmentStatus { get; init; }

    [JsonPropertyName("direction")]
    public required TickerPriceDirection Direction { get; init; }

    [JsonPropertyName("expected_price_min")]
    public double? ExpectedPriceMin { get; init; }

    [JsonPropertyName("expected_price_max")]
    public double? ExpectedPriceMax { get; init; }

    [JsonPropertyName("expected_return_min_pct")]
    public double? ExpectedReturnMinPct { get; init; }

    [JsonPropertyName("expected_return_max_pct")]
    public double? ExpectedReturnMaxPct { get; init; }

    [JsonPropertyName("confidence")]
    public required int Confidence { get; init; }

    [JsonPropertyName("rationale")]
    public required string Rationale { get; init; }

    [JsonPropertyName("key_drivers")]
    public required IReadOnlyList<string> KeyDrivers { get; init; }

    [JsonPropertyName("risk_factors")]
    public required IReadOnlyList<string> RiskFactors { get; init; }

    [JsonPropertyName("assumptions")]
    public required IReadOnlyList<string> Assumptions { get; init; }

    [JsonPropertyName("data_gaps")]
    public required IReadOnlyList<string> DataGaps { get; init; }

    [JsonPropertyName("reference_ids")]
    public required IReadOnlyList<string> ReferenceIds { get; init; }
}
