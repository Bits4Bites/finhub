using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Listings;

public sealed record ListingOutlook
{
    [JsonPropertyName("ipo_day")]
    public required ListingPeriodOutlook IpoDay { get; init; }

    [JsonPropertyName("first_week")]
    public required ListingPeriodOutlook FirstWeek { get; init; }

    [JsonPropertyName("first_two_weeks")]
    public required ListingPeriodOutlook FirstTwoWeeks { get; init; }

    [JsonPropertyName("first_month")]
    public required ListingPeriodOutlook FirstMonth { get; init; }
}
