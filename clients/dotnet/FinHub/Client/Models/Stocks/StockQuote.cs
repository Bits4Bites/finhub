using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Stocks;

public sealed record StockQuote
{
    [JsonPropertyName("currency")]
    public string? Currency { get; init; } = string.Empty;

    [JsonPropertyName("market_price")]
    public decimal? MarketPrice { get; init; } = 0.0m;

    [JsonPropertyName("market_price_change")]
    public decimal? MarketPriceChange { get; init; }

    [JsonPropertyName("market_price_change_percent")]
    public decimal? MarketPriceChangePercent { get; init; }

    [JsonPropertyName("market_open")]
    public decimal? MarketOpen { get; init; }

    [JsonPropertyName("market_day_high")]
    public decimal? MarketDayHigh { get; init; }

    [JsonPropertyName("market_day_low")]
    public decimal? MarketDayLow { get; init; }

    [JsonPropertyName("fifty_two_week_high")]
    public decimal? FiftyTwoWeekHigh { get; init; }

    [JsonPropertyName("fifty_two_week_low")]
    public decimal? FiftyTwoWeekLow { get; init; }

    [JsonPropertyName("market_volume")]
    public long? MarketVolume { get; init; }

    [JsonPropertyName("bid")]
    public decimal? Bid { get; init; }

    [JsonPropertyName("bid_size")]
    public long? BidSize { get; init; }

    [JsonPropertyName("ask")]
    public decimal? Ask { get; init; }

    [JsonPropertyName("ask_size")]
    public long? AskSize { get; init; }

    [JsonPropertyName("market_cap")]
    public long? MarketCap { get; init; }

    [JsonPropertyName("trailing_eps")]
    public decimal? TrailingEps { get; init; }

    [JsonPropertyName("forward_eps")]
    public decimal? ForwardEps { get; init; }

    [JsonPropertyName("trailing_p_e")]
    public decimal? TrailingPE { get; init; }

    [JsonPropertyName("forward_p_e")]
    public decimal? ForwardPE { get; init; }

    [JsonPropertyName("beta")]
    public decimal? Beta { get; init; }

    [JsonPropertyName("recommendation_key")]
    public string? RecommendationKey { get; init; }

    [JsonPropertyName("target_high_price")]
    public decimal? TargetHighPrice { get; init; }

    [JsonPropertyName("target_low_price")]
    public decimal? TargetLowPrice { get; init; }

    [JsonPropertyName("target_mean_price")]
    public decimal? TargetMeanPrice { get; init; }

    [JsonPropertyName("target_median_price")]
    public decimal? TargetMedianPrice { get; init; }

    /// <summary>
    /// 0: No change
    /// -1: Down
    /// 1: Up
    /// </summary>
    [JsonIgnore]
    public int MarketPriceStatus => MarketPriceChange == 0 ? 0 : (MarketPriceChange < 0 ? -1 : 1);

    /// <summary>
    /// 0: No change
    /// -1: Down
    /// 1: Up
    /// </summary>
    [JsonIgnore]
    public int EpsStatus => TrailingEps == ForwardEps ? 0 : (TrailingEps > ForwardEps ? -1 : 1);
}
