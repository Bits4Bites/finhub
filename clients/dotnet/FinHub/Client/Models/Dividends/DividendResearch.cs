using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Dividends;

public sealed record DividendResearch
{
    [JsonPropertyName("dividend_terms")]
    public required DividendEvidenceSection DividendTerms { get; init; }

    [JsonPropertyName("issuer_outlook")]
    public required DividendEvidenceSection IssuerOutlook { get; init; }

    [JsonPropertyName("event_risks")]
    public required DividendEvidenceSection EventRisks { get; init; }

    [JsonPropertyName("market_context")]
    public required DividendEvidenceSection MarketContext { get; init; }
}
