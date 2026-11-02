using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Tickers;

[JsonConverter(typeof(JsonStringEnumConverter<TickerAnalysisStatus>))]
public enum TickerAnalysisStatus
{
    Complete,
    CompleteWithWarnings,
}
