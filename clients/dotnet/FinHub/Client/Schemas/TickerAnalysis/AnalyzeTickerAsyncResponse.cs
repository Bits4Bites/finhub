using TickerAnalysisModel = FinHub.Client.Models.Tickers.TickerAnalysis;

namespace FinHub.Client.Schemas.TickerAnalysis;

public sealed class AnalyzeTickerAsyncResponse : AsyncApiResponse<TickerAnalysisModel>
{
    public AnalyzeTickerResponse ToApiResp()
    {
        return ToApiResp<AnalyzeTickerResponse>();
    }
}
