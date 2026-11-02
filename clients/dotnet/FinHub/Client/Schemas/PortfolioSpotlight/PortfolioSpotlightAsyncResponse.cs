using FinHub.Client.Models.Portfolios;
using MyPo.Shared.Api;

namespace FinHub.Client.Schemas.PortfolioSpotlight;

public sealed class PortfolioSpotlightAsyncResponse : AsyncApiResponse<PortfolioSpotlightAnalysis>
{
    public PortfolioSpotlightResponse ToApiResp()
    {
        return ToApiResp<PortfolioSpotlightResponse>();
    }
}
