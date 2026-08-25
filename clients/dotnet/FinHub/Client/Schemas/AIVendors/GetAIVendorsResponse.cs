using FinHub.Client.Models.AI;
using FinHub.Client.Schemas;

namespace FinHub.Client.Schemas.AIVendors;

public sealed record GetAIVendorsResponse : ApiResponseWithExtra<IReadOnlyDictionary<string, AIVendorInfo>>;
