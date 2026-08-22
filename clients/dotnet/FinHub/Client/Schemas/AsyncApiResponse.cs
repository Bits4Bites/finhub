using System.Text.Json.Serialization;

namespace FinHub.Client.Schemas;

public abstract record AsyncApiResponse<TData> : ApiResponse<TData>
{
    [JsonPropertyName("extra")]
    public required AsyncTaskInfo Extra { get; init; }
}
