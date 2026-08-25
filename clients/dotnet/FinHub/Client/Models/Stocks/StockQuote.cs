using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Stocks;

public sealed record StockQuote
{
    [JsonPropertyName("currency")]
    public string? Currency { get; init; } = string.Empty;

    [JsonPropertyName("market_price")]
    public double? MarketPrice { get; init; } = 0.0;

    [JsonPropertyName("market_price_change")]
    public double? MarketPriceChange { get; init; }

    [JsonPropertyName("market_price_change_percent")]
    public double? MarketPriceChangePercent { get; init; }

    [JsonPropertyName("market_open")]
    public double? MarketOpen { get; init; }

    [JsonPropertyName("market_day_high")]
    public double? MarketDayHigh { get; init; }

    [JsonPropertyName("market_day_low")]
    public double? MarketDayLow { get; init; }

    [JsonPropertyName("fifty_two_week_high")]
    public double? FiftyTwoWeekHigh { get; init; }

    [JsonPropertyName("fifty_two_week_low")]
    public double? FiftyTwoWeekLow { get; init; }

    [JsonPropertyName("market_volume")]
    public long? MarketVolume { get; init; }

    [JsonPropertyName("bid")]
    public double? Bid { get; init; }

    [JsonPropertyName("bid_size")]
    public long? BidSize { get; init; }

    [JsonPropertyName("ask")]
    public double? Ask { get; init; }

    [JsonPropertyName("ask_size")]
    public long? AskSize { get; init; }

    [JsonPropertyName("market_cap")]
    public long? MarketCap { get; init; }

    [JsonPropertyName("trailing_eps")]
    public double? TrailingEps { get; init; }

    [JsonPropertyName("forward_eps")]
    public double? ForwardEps { get; init; }

    [JsonPropertyName("trailing_p_e")]
    public double? TrailingPE { get; init; }

    [JsonPropertyName("forward_p_e")]
    public double? ForwardPE { get; init; }

    [JsonPropertyName("beta")]
    public double? Beta { get; init; }

    [JsonPropertyName("recommendation_key")]
    public string? RecommendationKey { get; init; }

    [JsonPropertyName("target_high_price")]
    public double? TargetHighPrice { get; init; }

    [JsonPropertyName("target_low_price")]
    public double? TargetLowPrice { get; init; }

    [JsonPropertyName("target_mean_price")]
    public double? TargetMeanPrice { get; init; }

    [JsonPropertyName("target_median_price")]
    public double? TargetMedianPrice { get; init; }
}
