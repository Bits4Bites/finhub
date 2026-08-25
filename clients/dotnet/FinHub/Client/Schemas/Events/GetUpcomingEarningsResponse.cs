using FinHub.Client.Models.Events;
using FinHub.Client.Schemas;

namespace FinHub.Client.Schemas.Events;

public sealed record GetUpcomingEarningsResponse
    : ApiResponseWithExtra<IReadOnlyList<UpcomingEarningsEvent>>;
