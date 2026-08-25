using FinHub.Client.Models.Events;
using FinHub.Client.Schemas;

namespace FinHub.Client.Schemas.Events;

public sealed record GetUpcomingDividendsAsyncResponse
    : AsyncApiResponse<IReadOnlyList<UpcomingDividendEvent>>;
