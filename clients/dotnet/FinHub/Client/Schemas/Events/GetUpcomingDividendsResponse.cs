using FinHub.Client.Models.Events;
using MyPo.Shared.Api;

namespace FinHub.Client.Schemas.Events;

public sealed class GetUpcomingDividendsResponse
    : ApiResp<IReadOnlyList<UpcomingDividendEvent>?>;
