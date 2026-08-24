using System.Text.Json.Serialization;

namespace FinHub.Client.Models.AI;

public sealed record ReferenceSource
{
    [JsonPropertyName("id")]
    public required string Id { get; init; }

    [JsonPropertyName("title")]
    public required string Title { get; init; }

    [JsonPropertyName("publisher")]
    public required string Publisher { get; init; }

    [JsonPropertyName("source_type")]
    public required ReferenceSourceType SourceType { get; init; }

    [JsonPropertyName("published_at")]
    public required DateTimeOffset? PublishedAt { get; init; }

    [JsonPropertyName("accessed_at")]
    public required DateTimeOffset AccessedAt { get; init; }

    [JsonPropertyName("url")]
    public required Uri Url { get; init; }

    [JsonPropertyName("is_verified")]
    public required bool IsVerified { get; init; }
}
