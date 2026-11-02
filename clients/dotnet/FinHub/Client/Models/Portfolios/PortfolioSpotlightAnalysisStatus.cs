using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Portfolios;

[JsonConverter(typeof(JsonStringEnumConverter<PortfolioSpotlightAnalysisStatus>))]
public enum PortfolioSpotlightAnalysisStatus
{
    Complete,
    CompleteWithWarnings,
}
