using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Portfolios;

[JsonConverter(typeof(PortfolioSpotlightRebalanceFlagJsonConverter))]
public enum PortfolioSpotlightRebalanceFlag
{
    Yes,
    No,
}
