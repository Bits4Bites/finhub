using MyPo.Shared.Api;
using TickerAnalysisModel = FinHub.Client.Models.Tickers.TickerAnalysis;

namespace FinHub.Client.Schemas.TickerAnalysis;

public sealed class AnalyzeTickerResponse : ApiResp<TickerAnalysisModel?>;
