using FinHub.Client.Models.Dividends;
using FinHub.Client.Schemas;

namespace FinHub.Client.Schemas.DividendAnalysis;

public sealed record AnalyzeDividendEventResponse : ApiResponseWithExtra<DividendEventAnalysis?>;
