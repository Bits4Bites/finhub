using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Portfolios;

public sealed record PortfolioReviewStrength
{
    [JsonPropertyName("title")]
    public required string Title { get; init; }

    [JsonPropertyName("analysis")]
    public required string Analysis { get; init; }

    [JsonPropertyName("affected_tickers")]
    public required IReadOnlyList<string> AffectedTickers { get; init; }

    [JsonPropertyName("confidence")]
    public required int Confidence { get; init; }

    [JsonPropertyName("data_gaps")]
    public required IReadOnlyList<string> DataGaps { get; init; }

    [JsonPropertyName("reference_ids")]
    public required IReadOnlyList<string> ReferenceIds { get; init; }
}
