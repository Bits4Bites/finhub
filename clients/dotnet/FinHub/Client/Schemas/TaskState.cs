using System.Text.Json.Serialization;

namespace FinHub.Client.Schemas;

[JsonConverter(typeof(TaskStateJsonConverter))]
public enum TaskState
{
    Running,
    Completed,
    Failed,
}
