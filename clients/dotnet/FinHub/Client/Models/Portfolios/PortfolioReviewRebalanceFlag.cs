using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Portfolios;

[JsonConverter(typeof(JsonStringEnumConverter<PortfolioReviewRebalanceFlag>))]
public enum PortfolioReviewRebalanceFlag
{
    YES,
    NO,
}
