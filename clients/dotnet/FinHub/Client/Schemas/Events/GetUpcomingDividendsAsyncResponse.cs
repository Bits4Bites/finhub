using FinHub.Client.Models.Dividends;
using MyPo.Shared.Api;

namespace FinHub.Client.Schemas.Events;

public sealed class GetUpcomingDividendsAsyncResponse : AsyncApiResponse<IReadOnlyList<UpcomingDividendEvent>>
{
    public GetUpcomingDividendsResponse ToApiResp()
    {
        return ToApiResp<GetUpcomingDividendsResponse>();
    }
}
