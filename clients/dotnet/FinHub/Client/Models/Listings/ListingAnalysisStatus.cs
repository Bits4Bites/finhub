using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Listings;

[JsonConverter(typeof(JsonStringEnumConverter<ListingAnalysisStatus>))]
public enum ListingAnalysisStatus
{
    NotStarted,
    Completed,
    Failed,
}
