using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Portfolios;

[JsonConverter(typeof(JsonStringEnumConverter<PortfolioSpotlightRiskLevel>))]
public enum PortfolioSpotlightRiskLevel
{
    Critical,
    High,
    Medium,
}
