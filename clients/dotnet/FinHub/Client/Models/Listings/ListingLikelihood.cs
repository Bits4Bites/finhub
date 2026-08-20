using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Listings;

[JsonConverter(typeof(JsonStringEnumConverter<ListingLikelihood>))]
public enum ListingLikelihood
{
    High,
    Medium,
    Low,
}
