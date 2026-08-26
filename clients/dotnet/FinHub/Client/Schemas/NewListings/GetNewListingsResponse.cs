using FinHub.Client.Models.Listings;
using MyPo.Shared.Api;

namespace FinHub.Client.Schemas.NewListings;

public sealed class GetNewListingsResponse : ApiResp<IReadOnlyList<ListingEvent>?>;
