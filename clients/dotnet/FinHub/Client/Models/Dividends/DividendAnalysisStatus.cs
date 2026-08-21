using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Dividends;

[JsonConverter(typeof(JsonStringEnumConverter<DividendAnalysisStatus>))]
public enum DividendAnalysisStatus
{
    Complete,
    CompleteWithWarnings,
    Failed,
}
