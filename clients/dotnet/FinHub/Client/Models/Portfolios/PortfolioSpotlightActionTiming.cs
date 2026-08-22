using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Portfolios;

[JsonConverter(typeof(JsonStringEnumConverter<PortfolioSpotlightActionTiming>))]
public enum PortfolioSpotlightActionTiming
{
    AsSoonAsPossibleWithinOneWeek,
    WithinOneToTwoWeeks,
    Monitor,
}
