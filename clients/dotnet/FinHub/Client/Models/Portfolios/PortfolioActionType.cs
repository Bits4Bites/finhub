using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Portfolios;

[JsonConverter(typeof(JsonStringEnumConverter<PortfolioActionType>))]
public enum PortfolioActionType
{
    EXIT,
    TRIM,
    BUY,
    ACCUMULATE,
    HOLD,
}
