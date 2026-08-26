using FinHub.Client.Schemas;
using TickerAnalysisModel = FinHub.Client.Models.Tickers.TickerAnalysis;

namespace FinHub.Client.Schemas.TickerAnalysis;

public sealed record AnalyzeTickerAsyncResponse : AsyncApiResponse<TickerAnalysisModel?>;
