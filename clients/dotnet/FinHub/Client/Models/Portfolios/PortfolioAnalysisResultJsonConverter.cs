using System.Text.Json;
using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Portfolios;

public sealed class PortfolioAnalysisResultJsonConverter : JsonConverter<IPortfolioAnalysisResult>
{
    public override IPortfolioAnalysisResult Read(
        ref Utf8JsonReader reader,
        Type typeToConvert,
        JsonSerializerOptions options
    )
    {
        using var document = JsonDocument.ParseValue(ref reader);
        if (document.RootElement.ValueKind != JsonValueKind.Object)
        {
            throw new JsonException("Portfolio analysis result must be a JSON object.");
        }

        if (!document.RootElement.TryGetProperty("result_type", out var resultTypeElement))
        {
            throw new JsonException(
                "Portfolio analysis result is missing the 'result_type' discriminator."
            );
        }

        if (resultTypeElement.ValueKind != JsonValueKind.String)
        {
            throw new JsonException(
                "Portfolio analysis result 'result_type' discriminator must be a string."
            );
        }

        return resultTypeElement.GetString() switch
        {
            "PortfolioConstruction" => document.RootElement.Deserialize<PortfolioConstruction>(options)
                ?? throw new JsonException("Portfolio construction result cannot be null."),
            "PortfolioReview" => document.RootElement.Deserialize<PortfolioReview>(options)
                ?? throw new JsonException("Portfolio review result cannot be null."),
            var resultType => throw new JsonException(
                $"Unknown portfolio analysis result_type discriminator '{resultType}'."
            ),
        };
    }

    public override void Write(
        Utf8JsonWriter writer,
        IPortfolioAnalysisResult value,
        JsonSerializerOptions options
    )
    {
        switch (value)
        {
            case PortfolioConstruction construction:
                JsonSerializer.Serialize(writer, construction, options);
                break;
            case PortfolioReview review:
                JsonSerializer.Serialize(writer, review, options);
                break;
            default:
                throw new JsonException(
                    $"Unsupported portfolio analysis result type '{value.GetType().FullName}'."
                );
        }
    }
}
