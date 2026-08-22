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
        var resultType = document.RootElement.TryGetProperty("construction_mode", out _)
            ? typeof(PortfolioConstruction)
            : typeof(AnalyzePortfolioResult);
        return (IPortfolioAnalysisResult)(
            document.RootElement.Deserialize(resultType, options)
            ?? throw new JsonException("Portfolio analysis result cannot be null.")
        );
    }

    public override void Write(
        Utf8JsonWriter writer,
        IPortfolioAnalysisResult value,
        JsonSerializerOptions options
    )
    {
        JsonSerializer.Serialize(writer, value, value.GetType(), options);
    }
}
