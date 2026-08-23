using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Portfolios;

[JsonConverter(typeof(JsonStringEnumConverter<PortfolioReviewStatus>))]
public enum PortfolioReviewStatus
{
    Complete,
    CompleteWithWarnings,
}
