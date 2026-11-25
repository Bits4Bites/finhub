using FinHub.Client.Models.Earnings;
using MyPo.Shared.Api;

namespace FinHub.Client.Schemas.Events;

public sealed class GetUpcomingEarningsResponse : ApiResp<IReadOnlyList<UpcomingEarningsEvent>>;
