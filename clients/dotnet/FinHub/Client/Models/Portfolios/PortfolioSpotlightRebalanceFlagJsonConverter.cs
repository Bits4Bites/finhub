using System.Text.Json;
using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Portfolios;

internal sealed class PortfolioSpotlightRebalanceFlagJsonConverter
    : JsonConverter<PortfolioSpotlightRebalanceFlag>
{
    public override PortfolioSpotlightRebalanceFlag Read(
        ref Utf8JsonReader reader,
        Type typeToConvert,
        JsonSerializerOptions options)
    {
        if (reader.TokenType != JsonTokenType.String)
        {
            throw new JsonException("Portfolio spotlight rebalance flag must be a string.");
        }

        return reader.GetString() switch
        {
            "YES" => PortfolioSpotlightRebalanceFlag.Yes,
            "NO" => PortfolioSpotlightRebalanceFlag.No,
            var value => throw new JsonException($"Unknown portfolio spotlight rebalance flag '{value}'."),
        };
    }

    public override void Write(
        Utf8JsonWriter writer,
        PortfolioSpotlightRebalanceFlag value,
        JsonSerializerOptions options)
    {
        writer.WriteStringValue(value switch
        {
            PortfolioSpotlightRebalanceFlag.Yes => "YES",
            PortfolioSpotlightRebalanceFlag.No => "NO",
            _ => throw new JsonException($"Unknown portfolio spotlight rebalance flag '{value}'."),
        });
    }
}
