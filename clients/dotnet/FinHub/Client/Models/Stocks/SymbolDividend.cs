using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Stocks;

public sealed record SymbolDividend
{
    [JsonPropertyName("dividend_rate")]
    public decimal DividendRate { get; init; } = 0.0m;

    [JsonPropertyName("dividend_yield")]
    public decimal DividendYield { get; init; } = 0.0m;

    [JsonPropertyName("payout_frequency")]
    public int PayoutFrequency { get; init; } = 0;

    [JsonPropertyName("ex_dividend_date")]
    public long ExDividendTimestamp { get; init; } = 0;

    [JsonPropertyName("ex_dividend_date_str")]
    public string? ExDividendTimestampStr { get; init; }

    [JsonIgnore]
    public DateTimeOffset ExDividendDate => !string.IsNullOrEmpty(ExDividendTimestampStr)
        ? DateTimeOffset.TryParse(ExDividendTimestampStr, out var dt) ? dt : DateTimeOffset.FromUnixTimeSeconds(ExDividendTimestamp)
        : DateTimeOffset.FromUnixTimeSeconds(ExDividendTimestamp);

    [JsonPropertyName("five_year_avg_dividend_yield")]
    public decimal FiveYearAvgDividendYield { get; init; } = 0.0m;

    [JsonPropertyName("trailing_annual_dividend_rate")]
    public decimal TrailingAnnualDividendRate { get; init; } = 0.0m;

    [JsonPropertyName("trailing_annual_dividend_yield")]
    public decimal TrailingAnnualDividendYield { get; init; } = 0.0m;

    [JsonPropertyName("last_dividend_value")]
    public decimal LastDividendValue { get; init; } = 0.0m;

    [JsonPropertyName("last_dividend_date")]
    public long LastDividendTimestamp { get; init; } = 0;

    [JsonPropertyName("last_dividend_date_str")]
    public string? LastDividendTimestampStr { get; init; }

    [JsonIgnore]
    public DateTimeOffset LastDividendDate => !string.IsNullOrEmpty(LastDividendTimestampStr)
        ? DateTimeOffset.TryParse(LastDividendTimestampStr, out var dt) ? dt : DateTimeOffset.FromUnixTimeSeconds(LastDividendTimestamp)
        : DateTimeOffset.FromUnixTimeSeconds(LastDividendTimestamp);
}
