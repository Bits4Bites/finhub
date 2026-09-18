using FinHub.Client.Models.Dividends;

namespace FinHub.Client.Schemas.DividendAnalysis;

public sealed class AnalyzeDividendEventAsyncResponse : AsyncApiResponse<DividendEventAnalysis>
{
    public AnalyzeDividendEventResponse ToApiResp()
    {
        return ToApiResp<AnalyzeDividendEventResponse>();
    }
}
