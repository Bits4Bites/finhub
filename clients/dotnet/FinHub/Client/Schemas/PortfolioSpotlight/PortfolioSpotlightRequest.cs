using System.Text.Json.Serialization;
using FinHub.Client.Models.Portfolios;

namespace FinHub.Client.Schemas.PortfolioSpotlight;

public sealed record PortfolioSpotlightRequest
{
    [JsonPropertyName("country")]
    public required string Country { get; init; }

    [JsonPropertyName("current_allocation")]
    public required IReadOnlyList<PortfolioHolding> CurrentAllocation { get; init; }

    [JsonPropertyName("investor_theme")]
    public required string InvestorTheme { get; init; }
}
