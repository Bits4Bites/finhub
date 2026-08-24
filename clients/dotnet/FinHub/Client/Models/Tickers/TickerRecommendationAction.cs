using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Tickers;

[JsonConverter(typeof(TickerRecommendationActionJsonConverter))]
public enum TickerRecommendationAction
{
    Buy,
    Hold,
    Sell,
}
