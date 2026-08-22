using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Portfolios;

public sealed record AnalyzePortfolioResult : IPortfolioAnalysisResult
{
    [JsonPropertyName("llm_error")]
    public bool LlmError { get; init; }

    [JsonPropertyName("llm_error_msg")]
    public string? LlmErrorMessage { get; init; }

    [JsonPropertyName("llm_response")]
    public string? LlmResponse { get; init; }

    [JsonPropertyName("analysis")]
    public string Analysis { get; init; } = "";

    [JsonPropertyName("rebalance_plan")]
    public string RebalancePlan { get; init; } = "";
}
