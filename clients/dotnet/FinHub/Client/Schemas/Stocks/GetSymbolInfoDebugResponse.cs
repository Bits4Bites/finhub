using System.Text.Json;
using FinHub.Client.Schemas;

namespace FinHub.Client.Schemas.Stocks;

public sealed record GetSymbolInfoDebugResponse : ApiResponseWithExtra<JsonElement?>;
