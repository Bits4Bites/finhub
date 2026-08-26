using FinHub.Client.Models.Stocks;
using FinHub.Client.Schemas;

namespace FinHub.Client.Schemas.Stocks;

public sealed record GetStockQuoteResponse : ApiResponseWithExtra<StockQuote?>;
