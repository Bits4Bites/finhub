using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Dividends;

[JsonConverter(typeof(JsonStringEnumConverter<DividendSampleQuality>))]
public enum DividendSampleQuality
{
    Sufficient,
    Limited,
}
