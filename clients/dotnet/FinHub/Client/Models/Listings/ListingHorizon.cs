using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Listings;

[JsonConverter(typeof(ListingHorizonJsonConverter))]
public enum ListingHorizon
{
    IpoDay,
    FirstWeek,
    FirstTwoWeeks,
    FirstMonth,
    LongerTerm,
}
