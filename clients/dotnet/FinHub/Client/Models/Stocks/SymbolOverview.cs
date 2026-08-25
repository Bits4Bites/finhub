using System.Text.Json.Serialization;
using FinHub.Client.Models.Tickers;

namespace FinHub.Client.Models.Stocks;

public record SymbolOverview : SymbolBase
{
    [JsonPropertyName("short_name")]
    public string? ShortName { get; init; }

    [JsonPropertyName("long_name")]
    public string? LongName { get; init; }

    [JsonPropertyName("sector")]
    public string? Sector { get; init; }

    [JsonPropertyName("industry")]
    public string? Industry { get; init; }

    [JsonPropertyName("website")]
    public string? Website { get; init; }

    [JsonPropertyName("description")]
    public string? Description { get; init; }

    [JsonPropertyName("quote_type")]
    public string? QuoteType { get; init; }

    [JsonPropertyName("asset_type")]
    public TickerAssetType? AssetType { get; init; }

    [JsonPropertyName("total_cash")]
    public long? TotalCash { get; init; }

    [JsonPropertyName("total_cash_per_share")]
    public double? TotalCashPerShare { get; init; }

    [JsonPropertyName("total_debt")]
    public long? TotalDebt { get; init; }

    [JsonPropertyName("total_debt_per_share")]
    public double? TotalDebtPerShare { get; init; }

    [JsonPropertyName("total_revenue")]
    public long? TotalRevenue { get; init; }

    [JsonPropertyName("total_revenue_per_share")]
    public double? TotalRevenuePerShare { get; init; }

    [JsonPropertyName("ebitda")]
    public long? Ebitda { get; init; }

    [JsonPropertyName("ebitda_margins")]
    public double? EbitdaMargins { get; init; }

    [JsonPropertyName("earnings_growth")]
    public double? EarningsGrowth { get; init; }

    [JsonPropertyName("revenue_growth")]
    public double? RevenueGrowth { get; init; }

    [JsonPropertyName("gross_margins")]
    public double? GrossMargins { get; init; }

    [JsonPropertyName("operating_margins")]
    public double? OperatingMargins { get; init; }

    [JsonPropertyName("profit_margins")]
    public double? ProfitMargins { get; init; }

    [JsonPropertyName("market_cap")]
    public long? MarketCap { get; init; }

    [JsonPropertyName("cap_size")]
    public MarketCapType? CapSize { get; init; }

    [JsonPropertyName("market_index")]
    public string? MarketIndex { get; init; }
}
