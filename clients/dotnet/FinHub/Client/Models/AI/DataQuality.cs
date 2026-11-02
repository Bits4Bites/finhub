using System.Text.Json.Serialization;

namespace FinHub.Client.Models.AI;

[JsonConverter(typeof(JsonStringEnumConverter<DataQuality>))]
public enum DataQuality
{
    High,
    Medium,
    Low,
    Insufficient,
}
