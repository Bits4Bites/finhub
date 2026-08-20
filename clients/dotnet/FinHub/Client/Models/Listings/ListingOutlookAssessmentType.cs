using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Listings;

[JsonConverter(typeof(JsonStringEnumConverter<ListingOutlookAssessmentType>))]
public enum ListingOutlookAssessmentType
{
    Forecast,
    Observed,
    InsufficientData,
}
