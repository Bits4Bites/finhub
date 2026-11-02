using System.Text.Json.Serialization;
using FinHub.Client.Models.AI;

namespace FinHub.Client.Models.Dividends;

public sealed record DividendResearch
{
    [JsonPropertyName("dividend_terms")]
    public required EvidenceSection DividendTerms { get; init; }

    [JsonPropertyName("issuer_outlook")]
    public required EvidenceSection IssuerOutlook { get; init; }

    [JsonPropertyName("event_risks")]
    public required EvidenceSection EventRisks { get; init; }

    [JsonPropertyName("market_context")]
    public required EvidenceSection MarketContext { get; init; }
}
