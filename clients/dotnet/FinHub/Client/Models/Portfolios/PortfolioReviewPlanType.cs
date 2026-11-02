using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Portfolios;

[JsonConverter(typeof(JsonStringEnumConverter<PortfolioReviewPlanType>))]
public enum PortfolioReviewPlanType
{
    Growth,
    Rebalance,
}
