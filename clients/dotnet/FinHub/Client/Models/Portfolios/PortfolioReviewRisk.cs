using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Portfolios;

public sealed record PortfolioReviewRisk
{
    [JsonPropertyName("level")]
    public required PortfolioReviewRiskLevel Level { get; init; }

    [JsonPropertyName("risk")]
    public required string Risk { get; init; }

    [JsonPropertyName("impact")]
    public required string Impact { get; init; }

    [JsonPropertyName("mitigation")]
    public required string Mitigation { get; init; }

    [JsonPropertyName("affected_tickers")]
    public required IReadOnlyList<string> AffectedTickers { get; init; }

    [JsonPropertyName("confidence")]
    public required int Confidence { get; init; }

    [JsonPropertyName("data_gaps")]
    public required IReadOnlyList<string> DataGaps { get; init; }

    [JsonPropertyName("reference_ids")]
    public required IReadOnlyList<string> ReferenceIds { get; init; }
}
