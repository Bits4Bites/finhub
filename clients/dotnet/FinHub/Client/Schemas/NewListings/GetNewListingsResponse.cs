using System.Text.Json;
using System.Text.Json.Serialization;
using FinHub.Client.Models.Listings;

namespace FinHub.Client.Schemas.NewListings;

public sealed record GetNewListingsResponse : ApiResponse<IReadOnlyList<ListingEvent>>
{
    [JsonPropertyName("extra")]
    public JsonElement? Extra { get; init; }
}
