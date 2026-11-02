using FinHub.Client.Models.Listings;
using MyPo.Shared.Api;

namespace FinHub.Client.Schemas.NewListings;

public sealed class GetNewListingsAsyncResponse : AsyncApiResponse<IReadOnlyList<ListingEvent>>
{
    public GetNewListingsResponse ToApiResp()
    {
        return ToApiResp<GetNewListingsResponse>();
    }
}
