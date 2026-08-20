using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Listings;

[JsonConverter(typeof(JsonStringEnumConverter<ListingOutlookDirection>))]
public enum ListingOutlookDirection
{
    Up,
    Flat,
    Down,
    InsufficientData,
}
