using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Listings;

public sealed record ListingGovernanceAnalysis : ListingAnalysisSection
{
    [JsonPropertyName("board_and_management")]
    public required string BoardAndManagement { get; init; }

    [JsonPropertyName("ownership_and_escrow")]
    public required string OwnershipAndEscrow { get; init; }

    [JsonPropertyName("governance_concerns")]
    public required IReadOnlyList<string> GovernanceConcerns { get; init; }
}
