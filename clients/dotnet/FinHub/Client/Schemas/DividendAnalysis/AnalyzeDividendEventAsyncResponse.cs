using System.Text.Json.Serialization;
using FinHub.Client.Models.Dividends;
using FinHub.Client.Schemas;

namespace FinHub.Client.Schemas.DividendAnalysis;

public sealed record AnalyzeDividendEventAsyncResponse : ApiResponse<DividendEventAnalysis>
{
    [JsonPropertyName("extra")]
    public required AsyncTaskInfo Extra { get; init; }
}
