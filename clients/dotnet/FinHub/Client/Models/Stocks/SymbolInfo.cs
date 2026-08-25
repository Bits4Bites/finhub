using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Stocks;

public sealed record SymbolInfo : SymbolOverview
{
    [JsonPropertyName("stock_quote")]
    public required StockQuote StockQuote { get; init; }

    [JsonPropertyName("dividend")]
    public required SymbolDividend Dividend { get; init; }

    [JsonPropertyName("stock_history")]
    public required StockHistory StockHistory { get; init; }
}
