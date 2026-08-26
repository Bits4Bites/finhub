using FinHub.Client.Schemas;
using PortfolioConstructionModel = FinHub.Client.Models.Portfolios.PortfolioConstruction;

namespace FinHub.Client.Schemas.PortfolioConstruction;

public sealed class BuildPortfolioAsyncResponse : AsyncApiResponse<PortfolioConstructionModel?>;
