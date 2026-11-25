using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Dividends;

public sealed record DividendTechnicalContext
{
    [JsonPropertyName("beta")]
    public double? Beta { get; init; }

    [JsonPropertyName("rsi14")]
    public double? Rsi14 { get; init; }

    [JsonPropertyName("average_daily_value_traded_7d")]
    public double? AverageDailyValueTraded7D { get; init; }

    [JsonPropertyName("average_volume_30d")]
    public double? AverageVolume30D { get; init; }

    [JsonPropertyName("daily_return_volatility_30d")]
    public double? DailyReturnVolatility30D { get; init; }

    [JsonPropertyName("bid_ask_spread")]
    public double? BidAskSpread { get; init; }

    [JsonPropertyName("stock_trend_60d")]
    public double? StockTrend60D { get; init; }

    [JsonPropertyName("market_trend_60d")]
    public double? MarketTrend60D { get; init; }

    [JsonPropertyName("peer_trend_60d")]
    public double? PeerTrend60D { get; init; }
}
