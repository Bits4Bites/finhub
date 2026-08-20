using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Listings;

[JsonConverter(typeof(JsonStringEnumConverter<ListingStatus>))]
public enum ListingStatus
{
    Upcoming,
    Listed,
}
