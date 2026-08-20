using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Listings;

public sealed record ListingFinancialAnalysis : ListingAnalysisSection
{
    [JsonPropertyName("historical_performance")]
    public required string HistoricalPerformance { get; init; }

    [JsonPropertyName("profitability_and_cash_flow")]
    public required string ProfitabilityAndCashFlow { get; init; }

    [JsonPropertyName("balance_sheet_and_funding")]
    public required string BalanceSheetAndFunding { get; init; }

    [JsonPropertyName("forecast_quality")]
    public required string ForecastQuality { get; init; }
}
