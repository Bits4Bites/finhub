using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Listings;

[JsonConverter(typeof(JsonStringEnumConverter<ListingStance>))]
public enum ListingStance
{
    Bullish,
    Neutral,
    Bearish,
    InsufficientData,
}
