using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Tickers;

[JsonConverter(typeof(JsonStringEnumConverter<TickerPriceDirection>))]
public enum TickerPriceDirection
{
    Up,
    Flat,
    Down,
    Mixed,
    InsufficientData,
}
