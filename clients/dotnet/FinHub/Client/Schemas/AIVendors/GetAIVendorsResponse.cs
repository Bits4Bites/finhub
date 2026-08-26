using System.Text.Json.Serialization;
using FinHub.Client.Models.AI;
using FinHub.Client.Schemas;

namespace FinHub.Client.Schemas.AIVendors;

public sealed record GetAIVendorsResponse
    : ApiResponseWithExtra<IReadOnlyDictionary<string, AIVendorInfo>>
{
    [JsonPropertyName("data")]
    public override IReadOnlyDictionary<string, AIVendorInfo> Data { get; init; } =
        new Dictionary<string, AIVendorInfo>();
}
