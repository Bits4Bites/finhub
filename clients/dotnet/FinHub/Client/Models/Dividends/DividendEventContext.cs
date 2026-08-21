using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Dividends;

public sealed record DividendEventContext
{
    [JsonPropertyName("symbol")]
    public required string Symbol { get; init; }

    [JsonPropertyName("exchange")]
    public required string Exchange { get; init; }

    [JsonPropertyName("company_name")]
    public required string? CompanyName { get; init; }

    [JsonPropertyName("currency")]
    public required string Currency { get; init; }

    [JsonPropertyName("country")]
    public required string? Country { get; init; }

    [JsonPropertyName("asset_type")]
    public required string AssetType { get; init; }

    [JsonPropertyName("exchange_timezone")]
    public required string ExchangeTimezone { get; init; }

    [JsonPropertyName("ex_date")]
    public required DateOnly ExDate { get; init; }

    [JsonPropertyName("phase")]
    public required DividendEventPhase Phase { get; init; }

    [JsonPropertyName("as_of")]
    public required DateTimeOffset AsOf { get; init; }

    [JsonPropertyName("reference_price")]
    public required double ReferencePrice { get; init; }

    [JsonPropertyName("dividend_amount")]
    public required double DividendAmount { get; init; }

    [JsonPropertyName("gross_dividend_yield")]
    public required double GrossDividendYield { get; init; }

    [JsonPropertyName("holding_period_days")]
    public required int HoldingPeriodDays { get; init; }

    [JsonPropertyName("transaction_costs")]
    public required DividendTransactionCosts TransactionCosts { get; init; }
}
