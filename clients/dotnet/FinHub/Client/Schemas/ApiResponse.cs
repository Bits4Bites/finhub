using System.Text.Json.Serialization;

namespace FinHub.Client.Schemas;

public abstract record ApiResponse<TData>
{
    [JsonPropertyName("status")]
    public required int Status { get; init; }

    [JsonPropertyName("message")]
    public required string Message { get; init; }

    [JsonPropertyName("data")]
    public virtual TData Data { get; init; } = default!;
}
