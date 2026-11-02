using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Portfolios;

[JsonConverter(typeof(JsonStringEnumConverter<PortfolioReviewRiskLevel>))]
public enum PortfolioReviewRiskLevel
{
    Critical,
    High,
    Medium,
    Low,
}
