using FinHub.Client.Models.Events;
using MyPo.Shared.Api;

namespace FinHub.Client.Schemas.Events;

public sealed class GetUpcomingEarningsAsyncResponse : AsyncApiResponse<IReadOnlyList<UpcomingEarningsEvent>>
{
    public GetUpcomingEarningsResponse ToApiResp()
    {
        return ToApiResp<GetUpcomingEarningsResponse>();
    }
}
