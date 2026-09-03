using FinHub.Client.Models.Listings;

namespace FinHub.Client.Schemas.NewListings;

public sealed class GetNewListingsAsyncResponse : AsyncApiResponse<IReadOnlyList<ListingEvent>>;
