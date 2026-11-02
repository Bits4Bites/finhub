using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Tickers;

[JsonConverter(typeof(TickerAssetTypeJsonConverter))]
public enum TickerAssetType
{
    Etf,
    MutualFund,
    Crypto,
    Reit,
    Lic,
    Hybrid,
    Standard,
    Other,
}
