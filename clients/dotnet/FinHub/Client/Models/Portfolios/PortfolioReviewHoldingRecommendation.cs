using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Portfolios;

[JsonConverter(typeof(JsonStringEnumConverter<PortfolioReviewHoldingRecommendation>))]
public enum PortfolioReviewHoldingRecommendation
{
    HOLD,
    TRIM,
    EXIT,
    BUY_MORE,
}
