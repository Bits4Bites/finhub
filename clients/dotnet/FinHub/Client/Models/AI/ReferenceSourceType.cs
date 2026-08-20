using System.Text.Json.Serialization;

namespace FinHub.Client.Models.AI;

[JsonConverter(typeof(JsonStringEnumConverter<ReferenceSourceType>))]
public enum ReferenceSourceType
{
    Regulatory,
    Exchange,
    Issuer,
    MarketData,
    Research,
    News,
    Other,
}
