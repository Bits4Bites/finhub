using System.Text.Json;
using System.Text.Json.Serialization;

namespace MyPo.Shared.Api;

/// <summary>
/// JSON converter for the <see cref="TaskState"/> enum.
/// </summary>
internal sealed class TaskStateJsonConverter : JsonConverter<TaskState>
{
    public override TaskState Read(
        ref Utf8JsonReader reader,
        Type typeToConvert,
        JsonSerializerOptions options)
    {
        if (reader.TokenType != JsonTokenType.String)
        {
            throw new JsonException("Task state must be a string.");
        }

        return reader.GetString() switch
        {
            "RUNNING" => TaskState.Running,
            "COMPLETED" => TaskState.Completed,
            "FAILED" => TaskState.Failed,
            var value => throw new JsonException($"Unknown task state '{value}'."),
        };
    }

    public override void Write(
        Utf8JsonWriter writer,
        TaskState value,
        JsonSerializerOptions options)
    {
        writer.WriteStringValue(value switch
        {
            TaskState.Running => "RUNNING",
            TaskState.Completed => "COMPLETED",
            TaskState.Failed => "FAILED",
            _ => throw new JsonException($"Unknown task state '{value}'."),
        });
    }
}

/// <summary>
/// Represents the state of an asynchronous task.
/// </summary>
[JsonConverter(typeof(TaskStateJsonConverter))]
public enum TaskState
{
    Running,
    Completed,
    Failed,
}

/// <summary>
/// Information about an asynchronous task.
/// </summary>
public sealed record AsyncTaskInfo
{
    [JsonPropertyName("task_id")]
    public required string TaskId { get; init; }

    [JsonPropertyName("state")]
    public TaskState? State { get; init; }
}

/// <summary>
/// Represents the response from an asynchronous API call, including task information.
/// </summary>
/// <typeparam name="TData">The type of the data returned by the API call.</typeparam>
public class AsyncApiResponse<TData> : ApiResp<TData>
{
    [JsonPropertyName("extra")]
    public new AsyncTaskInfo Extra
    {
        get => (AsyncTaskInfo)base.Extra!;
        init => base.Extra = value;
    }

    public virtual TResponse ToApiResp<TResponse>() where TResponse : ApiResp<TData>, new()
    {
        return new TResponse
        {
            Status = this.Status,
            Message = this.Message,
            Data = this.Data,
            Extra = this.Extra,
            DebugInfo = this.DebugInfo,
        };
    }
}
