using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Portfolios;

[JsonConverter(typeof(JsonStringEnumConverter<PortfolioReviewExitReason>))]
public enum PortfolioReviewExitReason
{
    CriticalRisk,
    StructuralChange,
    SwingRiskControl,
    SwingThesisInvalidated,
}
