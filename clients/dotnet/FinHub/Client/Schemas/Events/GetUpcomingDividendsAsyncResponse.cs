using FinHub.Client.Models.Events;
using MyPo.Shared.Api;

namespace FinHub.Client.Schemas.Events;

public sealed class GetUpcomingDividendsAsyncResponse : AsyncApiResponse<IReadOnlyList<UpcomingDividendEvent>>
{
    public GetUpcomingDividendsResponse ToApiResp()
    {
        return ToApiResp<GetUpcomingDividendsResponse>();
    }
}
