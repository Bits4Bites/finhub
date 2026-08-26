using MyPo.Shared.Api;
using PortfolioConstructionModel = FinHub.Client.Models.Portfolios.PortfolioConstruction;

namespace FinHub.Client.Schemas.PortfolioConstruction;

public sealed class BuildPortfolioResponse : ApiResp<PortfolioConstructionModel?>;
