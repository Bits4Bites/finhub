using System.Text.Json.Serialization;
using FinHub.Client.Models.Portfolios;

namespace FinHub.Client.Schemas.PortfolioConstruction;

public sealed record BuildPortfolioRequest
{
    [JsonPropertyName("country")]
    public required string Country { get; init; }

    [JsonPropertyName("investor_theme")]
    public required string InvestorTheme { get; init; }

    [JsonPropertyName("current_allocation")]
    public IReadOnlyList<PortfolioHolding> CurrentAllocation { get; init; } = [];
}
