using FinHub.Client.Models.Portfolios;

namespace FinHub.Client.Schemas.PortfolioSpotlight;

public sealed class PortfolioSpotlightAsyncResponse : AsyncApiResponse<PortfolioSpotlightAnalysis>
{
    public PortfolioSpotlightResponse ToApiResp()
    {
        return ToApiResp<PortfolioSpotlightResponse>();
    }
}
