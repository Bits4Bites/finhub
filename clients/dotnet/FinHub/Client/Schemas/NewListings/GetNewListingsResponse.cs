using FinHub.Client.Models.Listings;
using FinHub.Client.Schemas;

namespace FinHub.Client.Schemas.NewListings;

public sealed record GetNewListingsResponse : ApiResponseWithExtra<IReadOnlyList<ListingEvent>?>;
