using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Listings;

[JsonConverter(typeof(JsonStringEnumConverter<ListingDataQuality>))]
public enum ListingDataQuality
{
    High,
    Medium,
    Low,
    Insufficient,
}
