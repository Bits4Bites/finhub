using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Dividends;

[JsonConverter(typeof(JsonStringEnumConverter<DividendStrategyEligibility>))]
public enum DividendStrategyEligibility
{
    Eligible,
    Ineligible,
    InsufficientData,
}
