using System.Text.Json.Serialization;

namespace FinHub.Client.Schemas;

public sealed record AsyncTaskInfo
{
    [JsonPropertyName("task_id")]
    public required string TaskId { get; init; }

    [JsonPropertyName("state")]
    public TaskState? State { get; init; }
}
