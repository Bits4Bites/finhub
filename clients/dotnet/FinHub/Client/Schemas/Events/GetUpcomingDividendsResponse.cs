using FinHub.Client.Models.Dividends;
using MyPo.Shared.Api;

namespace FinHub.Client.Schemas.Events;

public sealed class GetUpcomingDividendsResponse : ApiResp<IReadOnlyList<UpcomingDividendEvent>>;
