using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Portfolios;

[JsonConverter(typeof(JsonStringEnumConverter<PortfolioBudgetType>))]
public enum PortfolioBudgetType
{
    NotProvided,
    Total,
    Recurring,
}
