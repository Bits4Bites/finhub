using FinHub.Client.Models.Stocks;
using MyPo.Shared.Api;

namespace FinHub.Client.Schemas.Stocks;

public sealed class GetStockHistoryResponse
    : ApiResp<IReadOnlyList<HistoryPoint>?>;
