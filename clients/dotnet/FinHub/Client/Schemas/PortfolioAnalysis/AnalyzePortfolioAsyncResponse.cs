using FinHub.Client.Models.Portfolios;

namespace FinHub.Client.Schemas.PortfolioAnalysis;

public sealed class AnalyzePortfolioAsyncResponse : AsyncApiResponse<IPortfolioAnalysisResult>
{
    public AnalyzePortfolioResponse ToApiResp()
    {
        return ToApiResp<AnalyzePortfolioResponse>();
    }
}
