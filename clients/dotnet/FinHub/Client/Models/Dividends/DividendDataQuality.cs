using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Dividends;

[JsonConverter(typeof(JsonStringEnumConverter<DividendDataQuality>))]
public enum DividendDataQuality
{
    High,
    Medium,
    Low,
    Insufficient,
}
