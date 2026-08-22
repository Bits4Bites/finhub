using System.Text.Json;
using System.Text.Json.Serialization;

namespace FinHub.Client.Schemas;

public abstract record ApiResponseWithExtra<TData> : ApiResponse<TData>
{
    [JsonPropertyName("extra")]
    public JsonElement? Extra { get; init; }
}
