using System.Text.Json.Serialization;

namespace FinHub.Client.Models.Dividends;

[JsonConverter(typeof(JsonStringEnumConverter<DividendStrategy>))]
public enum DividendStrategy
{
    DividendCapture,
    PostDividendDiscount,
}
