using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Portfolios;

[JsonConverter(typeof(JsonStringEnumConverter<PortfolioReviewActionType>))]
public enum PortfolioReviewActionType
{
    HOLD,
    TRIM,
    EXIT,
    BUY_MORE,
    INTRODUCE,
    ACCUMULATE,
}
