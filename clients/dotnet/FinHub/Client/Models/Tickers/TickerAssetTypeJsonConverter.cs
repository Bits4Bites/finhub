using System.Text.Json;
using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Tickers;

internal sealed class TickerAssetTypeJsonConverter : JsonConverter<TickerAssetType>
{
    public override TickerAssetType Read(
        ref Utf8JsonReader reader,
        Type typeToConvert,
        JsonSerializerOptions options)
    {
        if (reader.TokenType != JsonTokenType.String)
        {
            throw new JsonException("Ticker asset type must be a string.");
        }

        return reader.GetString() switch
        {
            "ETF" => TickerAssetType.Etf,
            "MUTUAL FUND" => TickerAssetType.MutualFund,
            "CRYPTO" => TickerAssetType.Crypto,
            "REIT" => TickerAssetType.Reit,
            "LIC" => TickerAssetType.Lic,
            "HYBRID" => TickerAssetType.Hybrid,
            "STANDARD" => TickerAssetType.Standard,
            "OTHER" => TickerAssetType.Other,
            var value => throw new JsonException($"Unknown ticker asset type '{value}'."),
        };
    }

    public override void Write(
        Utf8JsonWriter writer,
        TickerAssetType value,
        JsonSerializerOptions options)
    {
        writer.WriteStringValue(value switch
        {
            TickerAssetType.Etf => "ETF",
            TickerAssetType.MutualFund => "MUTUAL FUND",
            TickerAssetType.Crypto => "CRYPTO",
            TickerAssetType.Reit => "REIT",
            TickerAssetType.Lic => "LIC",
            TickerAssetType.Hybrid => "HYBRID",
            TickerAssetType.Standard => "STANDARD",
            TickerAssetType.Other => "OTHER",
            _ => throw new JsonException($"Unknown ticker asset type '{value}'."),
        });
    }
}
