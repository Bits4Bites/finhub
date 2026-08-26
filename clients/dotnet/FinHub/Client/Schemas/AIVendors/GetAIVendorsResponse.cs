using System.Diagnostics.CodeAnalysis;
using System.Text.Json.Serialization;
using FinHub.Client.Models.AI;
using MyPo.Shared.Api;

namespace FinHub.Client.Schemas.AIVendors;

public sealed class GetAIVendorsResponse
    : ApiResp<IReadOnlyDictionary<string, AIVendorInfo>>
{
    [AllowNull]
    [JsonPropertyName("data")]
    public override IReadOnlyDictionary<string, AIVendorInfo> Data { get; set; } =
        new Dictionary<string, AIVendorInfo>();
}
