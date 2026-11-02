using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Dividends;

[JsonConverter(typeof(JsonStringEnumConverter<DividendRecommendationOutcome>))]
public enum DividendRecommendationOutcome
{
    DividendCapture,
    PostDividendDiscount,
    NoClearWinner,
    InsufficientInsights,
}
