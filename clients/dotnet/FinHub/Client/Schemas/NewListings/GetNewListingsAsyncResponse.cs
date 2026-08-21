using System.Text.Json.Serialization;
using FinHub.Client.Models.Listings;
using FinHub.Client.Schemas;

namespace FinHub.Client.Schemas.NewListings;

public sealed record GetNewListingsAsyncResponse : ApiResponse<IReadOnlyList<ListingEvent>>
{
    [JsonPropertyName("extra")]
    public required AsyncTaskInfo Extra { get; init; }
}
