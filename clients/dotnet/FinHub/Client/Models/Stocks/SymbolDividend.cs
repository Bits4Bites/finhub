using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Stocks;

public sealed record SymbolDividend
{
    [JsonPropertyName("dividend_rate")]
    public double DividendRate { get; init; } = 0.0;

    [JsonPropertyName("dividend_yield")]
    public double DividendYield { get; init; } = 0.0;

    [JsonPropertyName("payout_frequency")]
    public int PayoutFrequency { get; init; } = 0;

    [JsonPropertyName("ex_dividend_date")]
    public long ExDividendDate { get; init; } = 0;

    [JsonPropertyName("ex_dividend_date_str")]
    public string? ExDividendDateStr { get; init; }

    [JsonPropertyName("five_year_avg_dividend_yield")]
    public double FiveYearAvgDividendYield { get; init; } = 0.0;

    [JsonPropertyName("trailing_annual_dividend_rate")]
    public double TrailingAnnualDividendRate { get; init; } = 0.0;

    [JsonPropertyName("trailing_annual_dividend_yield")]
    public double TrailingAnnualDividendYield { get; init; } = 0.0;

    [JsonPropertyName("last_dividend_value")]
    public double LastDividendValue { get; init; } = 0.0;

    [JsonPropertyName("last_dividend_date")]
    public long LastDividendDate { get; init; } = 0;

    [JsonPropertyName("last_dividend_date_str")]
    public string? LastDividendDateStr { get; init; }
}
