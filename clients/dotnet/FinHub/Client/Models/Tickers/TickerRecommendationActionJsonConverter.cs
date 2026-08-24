using System.Text.Json;
using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Tickers;

internal sealed class TickerRecommendationActionJsonConverter
    : JsonConverter<TickerRecommendationAction>
{
    public override TickerRecommendationAction Read(
        ref Utf8JsonReader reader,
        Type typeToConvert,
        JsonSerializerOptions options)
    {
        if (reader.TokenType != JsonTokenType.String)
        {
            throw new JsonException("Ticker recommendation action must be a string.");
        }

        return reader.GetString() switch
        {
            "BUY" => TickerRecommendationAction.Buy,
            "HOLD" => TickerRecommendationAction.Hold,
            "SELL" => TickerRecommendationAction.Sell,
            var value => throw new JsonException($"Unknown ticker recommendation action '{value}'."),
        };
    }

    public override void Write(
        Utf8JsonWriter writer,
        TickerRecommendationAction value,
        JsonSerializerOptions options)
    {
        writer.WriteStringValue(value switch
        {
            TickerRecommendationAction.Buy => "BUY",
            TickerRecommendationAction.Hold => "HOLD",
            TickerRecommendationAction.Sell => "SELL",
            _ => throw new JsonException($"Unknown ticker recommendation action '{value}'."),
        });
    }
}
