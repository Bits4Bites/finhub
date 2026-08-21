using System.Text.Json;
using System.Text.Json.Serialization;

namespace FinHub.Client.Schemas;

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
