using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Portfolios;

[JsonConverter(typeof(JsonStringEnumConverter<PortfolioReviewStrategy>))]
public enum PortfolioReviewStrategy
{
    LongTerm,
    Swing,
}
