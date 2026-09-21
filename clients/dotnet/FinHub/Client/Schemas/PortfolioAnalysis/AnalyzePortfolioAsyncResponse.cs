using FinHub.Client.Models.Portfolios;
using MyPo.Shared.Api;

namespace FinHub.Client.Schemas.PortfolioAnalysis;

public sealed class AnalyzePortfolioAsyncResponse : AsyncApiResponse<IPortfolioAnalysisResult>
{
    public AnalyzePortfolioResponse ToApiResp()
    {
        return ToApiResp<AnalyzePortfolioResponse>();
    }
}
