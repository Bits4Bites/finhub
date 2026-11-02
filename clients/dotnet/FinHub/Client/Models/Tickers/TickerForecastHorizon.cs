using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Tickers;

[JsonConverter(typeof(JsonStringEnumConverter<TickerForecastHorizon>))]
public enum TickerForecastHorizon
{
    OneWeek,
    TwoWeeks,
    OneMonth,
    ThreeMonths,
}
