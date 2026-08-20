using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Listings;

[JsonConverter(typeof(JsonStringEnumConverter<ListingRiskSeverity>))]
public enum ListingRiskSeverity
{
    Critical,
    High,
    Medium,
    Low,
}
