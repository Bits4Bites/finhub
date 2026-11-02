using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Tickers;

[JsonConverter(typeof(JsonStringEnumConverter<TickerRecommendationScope>))]
public enum TickerRecommendationScope
{
    NewPosition,
    ExistingHolding,
}
