using FinHub.Client.Models.Events;
using FinHub.Client.Schemas;

namespace FinHub.Client.Schemas.Events;

public sealed class GetUpcomingEarningsAsyncResponse
    : AsyncApiResponse<IReadOnlyList<UpcomingEarningsEvent>?>;
