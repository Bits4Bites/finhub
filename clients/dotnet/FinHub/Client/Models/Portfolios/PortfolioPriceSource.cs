using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Portfolios;

[JsonConverter(typeof(JsonStringEnumConverter<PortfolioPriceSource>))]
public enum PortfolioPriceSource
{
    MarketData,
    Client,
}
