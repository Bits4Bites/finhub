using System.Text.Json.Serialization;

namespace FinHub.Client.Models.AI;

public sealed record AIVendorInfo
{
    [JsonPropertyName("name")]
    public string Name { get; init; } = "";

    [JsonPropertyName("tier_models")]
    public IReadOnlyDictionary<string, IReadOnlyList<string>> TierModels { get; init; } =
        new Dictionary<string, IReadOnlyList<string>>();
}
