using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Dividends;

[JsonConverter(typeof(JsonStringEnumConverter<DividendEventPhase>))]
public enum DividendEventPhase
{
    BeforeExDate,
    ExDate,
    PostExDate,
    Historical,
}
