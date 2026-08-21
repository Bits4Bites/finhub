using System.Text.Json;
using System.Text.Json.Serialization;
using FinHub.Client.Models.Dividends;
using FinHub.Client.Schemas;

namespace FinHub.Client.Schemas.DividendAnalysis;

public sealed record AnalyzeDividendEventResponse : ApiResponse<DividendEventAnalysis>
{
    [JsonPropertyName("extra")]
    public JsonElement? Extra { get; init; }
}
