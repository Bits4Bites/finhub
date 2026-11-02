using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Portfolios;

[JsonConverter(typeof(JsonStringEnumConverter<PortfolioConstructionStatus>))]
public enum PortfolioConstructionStatus
{
    Complete,
    CompleteWithWarnings,
}
