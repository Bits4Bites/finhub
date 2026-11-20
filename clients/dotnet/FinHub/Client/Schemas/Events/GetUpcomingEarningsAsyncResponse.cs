using FinHub.Client.Models.Earnings;
using MyPo.Shared.Api;

namespace FinHub.Client.Schemas.Events;

public sealed class GetUpcomingEarningsAsyncResponse : AsyncApiResponse<IReadOnlyList<UpcomingEarningsEvent>>
{
    public GetUpcomingEarningsResponse ToApiResp()
    {
        return ToApiResp<GetUpcomingEarningsResponse>();
    }
}
