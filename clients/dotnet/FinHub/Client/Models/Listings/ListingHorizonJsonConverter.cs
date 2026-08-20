using System.Text.Json;
using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Listings;

internal sealed class ListingHorizonJsonConverter : JsonConverter<ListingHorizon>
{
    public override ListingHorizon Read(
        ref Utf8JsonReader reader,
        Type typeToConvert,
        JsonSerializerOptions options)
    {
        if (reader.TokenType != JsonTokenType.String)
        {
            throw new JsonException("Listing horizon must be a string.");
        }

        return reader.GetString() switch
        {
            "IPO Day" => ListingHorizon.IpoDay,
            "First Week" => ListingHorizon.FirstWeek,
            "First Two Weeks" => ListingHorizon.FirstTwoWeeks,
            "First Month" => ListingHorizon.FirstMonth,
            "Longer Term" => ListingHorizon.LongerTerm,
            var value => throw new JsonException($"Unknown listing horizon '{value}'."),
        };
    }

    public override void Write(
        Utf8JsonWriter writer,
        ListingHorizon value,
        JsonSerializerOptions options)
    {
        writer.WriteStringValue(value switch
        {
            ListingHorizon.IpoDay => "IPO Day",
            ListingHorizon.FirstWeek => "First Week",
            ListingHorizon.FirstTwoWeeks => "First Two Weeks",
            ListingHorizon.FirstMonth => "First Month",
            ListingHorizon.LongerTerm => "Longer Term",
            _ => throw new JsonException($"Unknown listing horizon '{value}'."),
        });
    }
}
