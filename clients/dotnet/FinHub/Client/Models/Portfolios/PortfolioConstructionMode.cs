using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Portfolios;

[JsonConverter(typeof(JsonStringEnumConverter<PortfolioConstructionMode>))]
public enum PortfolioConstructionMode
{
    Scratch,
    Seeded,
}
