using FinHub.Client.Models.Portfolios;
using FinHub.Client.Schemas;

namespace FinHub.Client.Schemas.PortfolioAnalysis;

public sealed record AnalyzePortfolioAsyncResponse : AsyncApiResponse<IPortfolioAnalysisResult?>;
