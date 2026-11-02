using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Portfolios;

[JsonConverter(typeof(PortfolioAnalysisResultJsonConverter))]
public interface IPortfolioAnalysisResult
{
    string ResultType { get; }
}
