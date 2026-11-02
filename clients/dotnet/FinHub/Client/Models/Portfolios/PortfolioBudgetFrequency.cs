using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Portfolios;

[JsonConverter(typeof(JsonStringEnumConverter<PortfolioBudgetFrequency>))]
public enum PortfolioBudgetFrequency
{
    Weekly,
    Fortnightly,
    Monthly,
    Quarterly,
    Annually,
}
