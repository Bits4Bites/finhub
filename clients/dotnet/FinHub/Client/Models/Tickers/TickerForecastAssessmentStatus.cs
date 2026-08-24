using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Tickers;

[JsonConverter(typeof(JsonStringEnumConverter<TickerForecastAssessmentStatus>))]
public enum TickerForecastAssessmentStatus
{
    Forecast,
    InsufficientData,
}
