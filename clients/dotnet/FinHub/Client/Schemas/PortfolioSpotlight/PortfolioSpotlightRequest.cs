using System.Text.Json.Serialization;
using FinHub.Client.Models.Portfolios;

namespace FinHub.Client.Schemas.PortfolioSpotlight;

public sealed record PortfolioSpotlightRequest
{
    [JsonPropertyName("country")]
    public required string Country { get; init; }

    [JsonPropertyName("current_allocation")]
    public IReadOnlyList<PortfolioHolding> CurrentAllocation { get; init; } = [];

    [JsonPropertyName("investor_theme")]
    public string? InvestorTheme { get; init; }
}
