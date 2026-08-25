using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Stocks;

[JsonConverter(typeof(JsonStringEnumConverter<MarketCapType>))]
public enum MarketCapType
{
    Large,
    Mid,
    Small,
    Micro,
    Nano,
}
